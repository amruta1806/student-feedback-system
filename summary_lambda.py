import json

import boto3

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('StudentFeedback')

RECENT_LIMIT = 10

HEADERS = {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': '*',
    'Cache-Control': 'no-store',
}


def scan_all():
    items = []
    kwargs = {}
    while True:
        page = table.scan(**kwargs)
        items.extend(page.get('Items', []))
        last_key = page.get('LastEvaluatedKey')
        if not last_key:
            return items
        kwargs['ExclusiveStartKey'] = last_key


def build_summary(items):
    distribution = {str(n): 0 for n in range(1, 6)}
    ratings = []
    comments = []

    for item in items:
        rating = str(item.get('rating', '')).strip()
        if rating in distribution:
            distribution[rating] += 1
            ratings.append(int(rating))

        comment = str(item.get('comment') or '').strip()
        if comment:
            # Names and roll numbers are left out on purpose.
            comments.append({
                'rating': rating,
                'comment': comment,
                'submitted_at': str(item.get('submitted_at', '')),
            })

    comments.sort(key=lambda entry: entry['submitted_at'], reverse=True)

    return {
        'count': len(ratings),
        'average': round(sum(ratings) / len(ratings), 1) if ratings else None,
        'distribution': distribution,
        'recent_comments': comments[:RECENT_LIMIT],
    }


def lambda_handler(event, context):
    try:
        summary = build_summary(scan_all())
    except Exception as error:
        print('Loading results failed: ' + str(error))
        return {
            'statusCode': 500,
            'headers': HEADERS,
            'body': json.dumps({'message': 'Results could not be loaded.'}),
        }

    return {'statusCode': 200, 'headers': HEADERS, 'body': json.dumps(summary)}
