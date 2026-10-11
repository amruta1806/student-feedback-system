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


def load_lambda():
    import lambda_function
    return importlib.reload(lambda_function)


@mock_aws
def test_feedback_is_stored_and_returns_200():
    table = make_table()
    lf = load_lambda()

    event = {
        "body": json.dumps(
            {"name": "Test Student", "rollno": "01", "rating": "5", "comment": "Great"}
        )
    }
    result = lf.lambda_handler(event, None)

    assert result["statusCode"] == 200
    assert json.loads(result["body"])["message"] == "Feedback submitted successfully"

    item = table.get_item(Key={"rollno": "01"})["Item"]
    assert item["name"] == "Test Student"
    assert item["rating"] == "5"
    assert item["comment"] == "Great"


@mock_aws
def test_same_rollno_overwrites_item():
    table = make_table()
    lf = load_lambda()

    for rating in ("3", "4"):
        event = {
            "body": json.dumps(
                {"name": "Test Student", "rollno": "02", "rating": rating, "comment": "ok"}
            )
        }
        assert lf.lambda_handler(event, None)["statusCode"] == 200

    assert table.get_item(Key={"rollno": "02"})["Item"]["rating"] == "4"
