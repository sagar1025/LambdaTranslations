# Translate Dynamic and Static data using AWS Lambda.
Dynamically translate data using AWS Lambda. This repo sets up the lambda function that will generate and store the translations.

This uses `Zappa` and `Python`

For demo purposes only Arabic is supported, but more languages can be added. To do this, just add the language iso code to the `validLangs` list.
The list of these codes can be found here: https://docs.aws.amazon.com/translate/latest/dg/what-is.html#what-is-languages

This Lambda function can translate text in 2 ways:
1. In Bulk (useful for static translations/static web pages)
2. Single line of text (useful when there is dynamic text such as form validation)

Initially since no translation exist, the first call takes a little longer (few seconds) than every other subsequent call.

If the translation does not exist, then the text is translated using AWS `translate_text` method. The hash of the original string and the translated text
are then stored in a dynamodb table called `Translations`.

In this table, the unique key is the `SrcString` which is the MD5 hash of the source string.

The `TranslatedText` column represents the translated text.
