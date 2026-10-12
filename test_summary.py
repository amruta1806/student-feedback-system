import importlib
import json
import os

import boto3
from moto import mock_aws

os.environ["AWS_DEFAULT_REGION"] = "ap-southeast-2"
os.environ["AWS_ACCESS_KEY_ID"] = "testing"
os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"


def make_table():
    ddb = boto3.resource("dynamodb")
    ddb.create_table(
        TableName="StudentFeedback",
        KeySchema=[{"AttributeName": "rollno", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "rollno", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )
    return ddb.Table("StudentFeedback")


def load_summary():
    import summary_lambda
    return importlib.reload(summary_lambda)


def add(table, rollno, rating, comment, submitted_at=None):
    item = {"rollno": rollno, "name": "Student " + rollno, "rating": rating, "comment": comment}
    if submitted_at:
        item["submitted_at"] = submitted_at
    table.put_item(Item=item)


@mock_aws
def test_empty_table_returns_zero_count_and_no_average():
    make_table()
    sl = load_summary()

    result = sl.lambda_handler({}, None)
    body = json.loads(result["body"])

    assert result["statusCode"] == 200
    assert body["count"] == 0
    assert body["average"] is None
    assert body["recent_comments"] == []


@mock_aws
def test_average_and_distribution_are_calculated():
    table = make_table()
    add(table, "01", "5", "")
    add(table, "02", "4", "")
    add(table, "03", "4", "")
    add(table, "04", "1", "")
    sl = load_summary()

    body = json.loads(sl.lambda_handler({}, None)["body"])

    assert body["count"] == 4
    assert body["average"] == 3.5
    assert body["distribution"] == {"1": 1, "2": 0, "3": 0, "4": 2, "5": 1}


@mock_aws
def test_recent_comments_are_newest_first_and_anonymous():
    table = make_table()
    add(table, "01", "5", "Older comment", "2026-10-10T09:00:00+00:00")
    add(table, "02", "3", "Newest comment", "2026-10-12T09:00:00+00:00")
    add(table, "03", "4", "")
    sl = load_summary()

    body = json.loads(sl.lambda_handler({}, None)["body"])
    comments = body["recent_comments"]

    assert [c["comment"] for c in comments] == ["Newest comment", "Older comment"]
    assert all(set(c) == {"rating", "comment", "submitted_at"} for c in comments)
    assert "Student 01" not in json.dumps(body)


@mock_aws
def test_only_ten_recent_comments_are_returned():
    table = make_table()
    for number in range(12):
        add(table, "%02d" % number, "5", "Comment " + str(number), "2026-10-12T09:%02d:00+00:00" % number)
    sl = load_summary()

    body = json.loads(sl.lambda_handler({}, None)["body"])

    assert len(body["recent_comments"]) == 10
    assert body["recent_comments"][0]["comment"] == "Comment 11"


@mock_aws
def test_results_allow_browser_access():
    make_table()
    sl = load_summary()

    headers = sl.lambda_handler({}, None)["headers"]

    assert headers["Access-Control-Allow-Origin"] == "*"
