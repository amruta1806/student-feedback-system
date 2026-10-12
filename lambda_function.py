import json
import os
from datetime import datetime, timezone

import boto3

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('StudentFeedback')

# Email alerts: set the environment variable SNS_TOPIC_ARN on the Lambda function
# (Configuration > Environment variables). When it is not set, no alert is sent.
sns_client = None

MAX_COMMENT_LENGTH = 500

HEADERS = {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': '*',
}


def respond(status_code, body):
    return {'statusCode': status_code, 'headers': HEADERS, 'body': json.dumps(body)}


def text(value):
    return '' if value is None else str(value).strip()


def parse_body(event):
    body = (event or {}).get('body')
    if body is None:
        raise ValueError('Request body is missing.')
    if isinstance(body, dict):
        return body
    try:
        data = json.loads(body)
    except (TypeError, ValueError):
        raise ValueError('Request body must be valid JSON.')
    if not isinstance(data, dict):
        raise ValueError('Request body must be a JSON object.')
    return data


def validate(data):
    name = text(data.get('name'))
    rollno = text(data.get('rollno'))
    rating = text(data.get('rating'))
    comment = text(data.get('comment'))

    if not name:
        raise ValueError('Name is required.')
    if not rollno:
        raise ValueError('Roll number is required.')
    if rating not in ('1', '2', '3', '4', '5'):
        raise ValueError('Rating must be a whole number from 1 to 5.')
    if len(comment) > MAX_COMMENT_LENGTH:
        raise ValueError('Comment must be 500 characters or fewer.')
    return name, rollno, rating, comment


def send_alert(name, rollno, rating, comment):
    topic_arn = os.environ.get('SNS_TOPIC_ARN')
    if not topic_arn:
        return
    try:
        client = sns_client or boto3.client('sns')
        client.publish(
            TopicArn=topic_arn,
            Subject='New feedback: ' + rating + ' out of 5',
            Message=(
                'A new response was saved.\n\n'
                'Name: ' + name + '\n'
                'Roll number: ' + rollno + '\n'
                'Rating: ' + rating + ' out of 5\n'
                'Comment: ' + (comment or '(none)')
            ),
        )
    except Exception as error:  # a failed alert must never lose the feedback
        print('SNS alert failed: ' + str(error))


def lambda_handler(event, context):
    try:
        name, rollno, rating, comment = validate(parse_body(event))
    except ValueError as error:
        return respond(400, {'message': str(error)})

    try:
        table.put_item(
            Item={
                'rollno': rollno,
                'name': name,
                'rating': rating,
                'comment': comment,
                'submitted_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
            }
        )
    except Exception as error:
        print('Saving feedback failed: ' + str(error))
        return respond(500, {'message': 'Feedback could not be saved. Try again.'})

    send_alert(name, rollno, rating, comment)

    return respond(200, {
        'message': 'Feedback submitted successfully',
        'name': name,
        'rollno': rollno,
        'rating': rating,
        'comment': comment,
    })
