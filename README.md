# Translate Dynamic and Static data using AWS Lambda.
Dynamically translate data using AWS Lambda. This repo sets up the lambda function that will generate and store the translations.

This uses `Zappa` and `Python`

For demo purposes only Arabic is supported, but more languages can be added. To do this, just add the language iso code to the `validLangs` list.
The list of these codes can be found here: https://docs.aws.amazon.com/translate/latest/dg/what-is.html#what-is-languages

This Lambda function can translate text in 2 ways:
1. In bulk such as a List or an Array of strings (useful for static translations/static web pages)
2. Single line of text (useful when there is dynamic text such as form validation)

Initially since no translation exist, the first call takes a little longer (few seconds) than every other subsequent call.

If the translation does not exist, then the text is translated using AWS `translate_text` method. The hash of the original string and the translated text
are then stored in a dynamodb table called `Translations`.

In this table, the unique key is the `SrcString` which is the MD5 hash of the source string. You may need this value when translating an array of texts.

The `TranslatedText` column represents the translated text.

___

### To run locally
1. Create a virtual environment called `venv`
2. `source venv/bin/activate`
3. `pip install -r requirements.txt`
4. `export FLASK_APP=translation.py`
5. `export ApiKey='123'` (Note: this is just used for testing. An actual Auth header value must be generated prior to a production release)
6. `flask run`

This should start a local wsgi development server. The application will be running on port `5000` by default.

You can now send requests to this endpoint.

## To Translate a single line of text:

#### Request:
<pre>
curl --location --request POST 'http://127.0.0.1:5000/translate' \
--header 'Authorization: Bearer 123' \
--header 'Content-Type: application/json' \
--data-raw '{
    "language": "ar",
    "txt": "hello world! please translate me!"
}'</pre>

#### Response:
<pre>
{
    "data": "مرحبا بالعالم! الرجاء ترجمة لي!",
    "isSuccess": true
}
</pre>

## To translate a list/array of texts:

#### Request:
<pre>
curl --location --request POST 'http://127.0.0.1:5000/translate' \
--header 'Authorization: Bearer 123' \
--header 'Content-Type: application/json' \
--data-raw '{
    "language": "ar",
    "TextList": ["hello world! please translate me!", "Hello World!"]
}'
</pre>

#### Response:
<pre>
{
    "data": [
        {
            "strHash": "a6b1e80a7a066436a369943c38f56f56",
            "translatedText": "عالم مرحبا!"
        },
        {
            "strHash": "03c53061de8fb588d9b407115a50402c",
            "translatedText": "مرحبا بالعالم! الرجاء ترجمة لي!"
        }
    ],
    "isSuccess": true
}
</pre>

Notice how the response is different. The frontend application can utilize the `strHash` to map the original string with the translated string.
