from flask import Flask, request, jsonify, abort
from flask_cors import CORS, cross_origin
import json
import logging
import boto3
from boto3.dynamodb.conditions import Key, Attr
from botocore.exceptions import ClientError
import re
import hashlib

app = Flask(__name__)

validLangs = ["ar","fr"]

#decorator to validate each api call
def Validate_API_Key(func):
    @wraps(func)
    def decorated_function(*args, **kwargs):
        #print(os.getenv('ApiKey'))
        if request.headers.get('Authorization'):
            token_header = request.headers['Authorization']
            auth_token = token_header.split(maxsplit=1)[1] #this removes the Bearer part of the value
            if auth_token == os.getenv('ApiKey'):
                return func(*args, **kwargs)
            else:
                logging.error('invalid APIKEY in header.')
                logging.error(request.headers.get('Authorization'))
                abort(401)
        else:
            logging.error('Auth header not present')
            logging.error(request.headers.get('Authorization'))
            abort(401)
    return decorated_function

def ValidData(txt):
    if isinstance(txt, str):
        return True if re.match("^[a-zA-Z0-9 ]*$", txt) else False
    return False

def chunks(l, n):
    for i in range(0, len(l), n):
        yield l[i:i + n]

def GetTranslation(txt, lang):
    #call to AWS translate
    boto_session = boto3.Session(region_name='us-east-1')
    translateClient = boto_session.client('translate')
    try:
        response = translateClient.translate_text(
            Text=txt,
            SourceLanguageCode='en',
            TargetLanguageCode=lang
        )
        if not "TranslatedText" in response:
            return None, False
        else:
            return response["TranslatedText"], True

    except ClientError as e:
        return None, False

    return None, False

def GetBulkTranslationFromDB(txtList,  lang):
    boto_session = boto3.Session(region_name='us-east-1')
    dynamodb = boto_session.resource('dynamodb')
    table = dynamodb.Table('Translations')
    returnResp =[]
    try:
        chunksList = chunks(txtList, 50)
        for chunk in chunksList:
            hashLstPair = [(hashlib.md5(txt.encode('utf-8')).hexdigest(),txt) for txt in chunk]
            # taken from https://github.com/awsdocs/aws-doc-sdk-examples/blob/211af2ea62cbdbd806bb59e74f54a6bc9d747ecc/python/example_code/dynamodb/batching/dynamo_batching.py
            #list of keys passed must be unique. This is why its converted to a set first. 
            batch_keys = {
                table.name: {
                    "Keys": [{"SrcString": md5hashTxt} for md5hashTxt, txt in list(set(hashLstPair))]
                }
            }
            try:
                tries = 0
                max_tries = 5
                sleepy_time = 1  # Start with 1 second of sleep, then exponentially increase.
                retrieved = {key: [] for key in batch_keys}
                while tries < max_tries:
                    response = dynamodb.batch_get_item(RequestItems=batch_keys)
                    # Collect any retrieved items and retry unprocessed keys.
                    for key in response.get('Responses', []):
                        retrieved[key] += response['Responses'][key]
                    unprocessed = response['UnprocessedKeys']
                    if len(unprocessed) > 0:
                        batch_keys = unprocessed
                        unprocessed_count = sum(
                            [len(batch_key['Keys']) for batch_key in batch_keys.values()])
                        logger.info("%s unprocessed keys returned. Sleep, then retry.", unprocessed_count)
                        tries += 1
                        if tries < max_tries:
                            logger.info("Sleeping for %s seconds.", sleepy_time)
                            time.sleep(sleepy_time)
                            sleepy_time = min(sleepy_time * 2, 32)
                    else:
                        break

                found_items = []
                for itm in retrieved['Translations']:
                    found_items.append(itm['SrcString'])

                
                hashLst = [item[0] for item in hashLstPair]

                # yields the elements in list_2 that are NOT in list_1. Basically figure out which hashed items were found and which were not found.
                not_found = [item for item in hashLst if item not in found_items]

                if not_found:
                    for hashTxt in not_found:
                        f = [item for item in hashLstPair if item[0] == hashTxt]
                        if f:
                            for elm in f:
                                translation, isSuccess = GetTranslationFromDB(elm[1], lang) #Get and Store the translation for the individual ones which were not found
                            if isSuccess:
                                tObj = {}
                                tObj['strHash'] = elm[0]
                                tObj['translatedText'] = translation
                                returnResp.append(tObj)
                            else:
                                print("Error. Cannot insert")
                
                #construct response object
                for itm in retrieved['Translations']:
                    tObj = {}
                    tObj['strHash'] = itm['SrcString']
                    tObj['translatedText'] = itm[lang]
                    returnResp.append(tObj)
            except Exception as e:
                print(e)
                return None, False

    except Exception as e:
        print(e)
        return None, False

    return returnResp, True


def GetTranslationFromDB(txt, lang):
    #if translation exists, return translation
    
    boto_session = boto3.Session(region_name='us-east-1')
    dynamodb = boto_session.resource('dynamodb')
    table = dynamodb.Table('Translations')

    try:
        md5hashTxt = hashlib.md5(txt.encode('utf-8')).hexdigest()
        response = table.get_item(Key = {"SrcString": md5hashTxt } )
        if "ResponseMetadata" in response and "HTTPStatusCode" in response["ResponseMetadata"] and response["ResponseMetadata"]["HTTPStatusCode"] == 200 \
            and "Item" in response:
            #valid response and key is found
            #print(response)
            #here lang is the "column" in the dynamodb table. For example, if "ar" is passed in the "ar" will contain the arabic text. See dynamodb table schema for more info
            if lang in response["Item"]:
                #translation exists
                return response["Item"][lang], True
            else:
                #Key exists in table but translation is not found. So fetch the new translation and append it to the existing Key.
                try:
                    #Fetch translation
                    translatedText, isSuccess = GetTranslation(txt, lang)
                    if isSuccess:
                        #update Existing Key
                        try:
                            updateResponse = table.update_item(
                                Key={
                                    "SrcString": md5hashTxt
                                },
                                UpdateExpression='SET ' + lang + ' = :languageCol',
                                ExpressionAttributeValues={
                                    ':languageCol': translatedText 
                                }
                            )
                            #print(updateResponse)
                            if "ResponseMetadata" in response and "HTTPStatusCode" in response["ResponseMetadata"] and response["ResponseMetadata"]["HTTPStatusCode"] == 200:
                                return translatedText, True
                        except Exception as e:
                            print(e)
                            
                except:
                    return None, False
        else:
            #Key does not exist. In this case, we fetch the translation and add a new Key to the table.
            try:
                #print("Adding new Key")
                translatedText, isSuccess = GetTranslation(txt, lang)
                if isSuccess:
                    #Add new Key and value pair to table
                    try:
                        addResponse = table.put_item(
                            Item={
                                "SrcString": md5hashTxt,
                                lang: translatedText
                            }
                        )
                        #print(addResponse)
                        if "ResponseMetadata" in response and "HTTPStatusCode" in response["ResponseMetadata"] and response["ResponseMetadata"]["HTTPStatusCode"] == 200:
                            return translatedText, True
                    except Exception as e:
                        print(e)
            except Exception as e:
                print(e)
                return None, False
    except ClientError as e:
        print(e.response['Error']['Message'])
        return None, False
    return None, False


@app.route('/translate', methods=['POST'])
@cross_origin()
#@Validate_API_Key
def Translate():
    if request.args is not None:
        data = request.get_json()
        if data and "language" in data and data["language"] in validLangs and ValidData(data["language"]):
            if "txt" in data and len(data["txt"]) > 0 and isinstance(data["txt"], str):
                txt, isSuccess = GetTranslationFromDB(data["txt"], data["language"])
                if isSuccess:
                    return jsonify(isSuccess= isSuccess, data = txt)
                else:
                    return jsonify(isSuccess= isSuccess, data = None)

            elif isinstance(data["TextList"], list):
                txt, isSuccess = GetBulkTranslationFromDB(data["TextList"], data["language"])

                if isSuccess:
                    return jsonify(isSuccess= isSuccess, data = txt)
                else:
                    return jsonify(isSuccess= isSuccess, data = None)
            else:
                return "Invalid Request", 400

        else:
            return "Invalid Request", 400
    return "Invalid Request", 400



if __name__ == '__main__':
    try:
        # #set debug/prod mode
        # if os.getenv('FLASK_ENV') == 'development':
        #     application.debug = True
        # else:
        #     application.debug = False

        application.run(threaded=True)
    except Exception as e:
        logging.error('Check Environment variables. Unable to start.', exc_info=True)