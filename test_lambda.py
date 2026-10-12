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


def event_with(**fields):
    return {"body": json.dumps(fields)}


class FakeSns:
    def __init__(self, fail=False):
        self.fail = fail
        self.published = []

    def publish(self, **kwargs):
        if self.fail:
            raise RuntimeError("SNS is down")
        self.published.append(kwargs)


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


@mock_aws
def test_saved_item_has_a_timestamp():
    table = make_table()
    lf = load_lambda()

    lf.lambda_handler(event_with(name="A", rollno="03", rating="4", comment="x"), None)

    assert table.get_item(Key={"rollno": "03"})["Item"]["submitted_at"].endswith("+00:00")


@mock_aws
def test_missing_name_returns_400():
    table = make_table()
    lf = load_lambda()

    result = lf.lambda_handler(event_with(name="  ", rollno="04", rating="4", comment=""), None)

    assert result["statusCode"] == 400
    assert json.loads(result["body"])["message"] == "Name is required."
    assert "Item" not in table.get_item(Key={"rollno": "04"})


@mock_aws
def test_rating_outside_range_returns_400():
    make_table()
    lf = load_lambda()

    for bad in ("0", "6", "abc", ""):
        result = lf.lambda_handler(event_with(name="A", rollno="05", rating=bad, comment=""), None)
        assert result["statusCode"] == 400


@mock_aws
def test_malformed_json_returns_400():
    make_table()
    lf = load_lambda()

    assert lf.lambda_handler({"body": "{not json"}, None)["statusCode"] == 400
    assert lf.lambda_handler({}, None)["statusCode"] == 400


@mock_aws
def test_comment_is_optional():
    table = make_table()
    lf = load_lambda()

    result = lf.lambda_handler({"body": json.dumps({"name": "A", "rollno": "06", "rating": "3"})}, None)

    assert result["statusCode"] == 200
    assert table.get_item(Key={"rollno": "06"})["Item"]["comment"] == ""


@mock_aws
def test_responses_allow_browser_access():
    make_table()
    lf = load_lambda()

    ok = lf.lambda_handler(event_with(name="A", rollno="07", rating="5", comment=""), None)
    bad = lf.lambda_handler(event_with(name="", rollno="07", rating="5", comment=""), None)

    assert ok["headers"]["Access-Control-Allow-Origin"] == "*"
    assert bad["headers"]["Access-Control-Allow-Origin"] == "*"


@mock_aws
def test_save_failure_returns_500():
    make_table()
    lf = load_lambda()

    class BrokenTable:
        def put_item(self, **kwargs):
            raise RuntimeError("DynamoDB is down")

    lf.table = BrokenTable()
    result = lf.lambda_handler(event_with(name="A", rollno="08", rating="5", comment=""), None)

    assert result["statusCode"] == 500


@mock_aws
def test_email_alert_is_sent_when_topic_is_configured():
    make_table()
    lf = load_lambda()
    fake = FakeSns()
    lf.sns_client = fake
    os.environ["SNS_TOPIC_ARN"] = "arn:aws:sns:ap-southeast-2:123456789012:feedback-alerts"
    try:
        result = lf.lambda_handler(
            event_with(name="Asha", rollno="09", rating="5", comment="Loved it"), None
        )
    finally:
        del os.environ["SNS_TOPIC_ARN"]

    assert result["statusCode"] == 200
    assert len(fake.published) == 1
    assert fake.published[0]["Subject"] == "New feedback: 5 out of 5"
    assert "Loved it" in fake.published[0]["Message"]


@mock_aws
def test_no_alert_without_topic():
    make_table()
    lf = load_lambda()
    fake = FakeSns()
    lf.sns_client = fake

    lf.lambda_handler(event_with(name="A", rollno="10", rating="5", comment=""), None)

    assert fake.published == []


@mock_aws
def test_alert_failure_does_not_lose_the_feedback():
    table = make_table()
    lf = load_lambda()
    lf.sns_client = FakeSns(fail=True)
    os.environ["SNS_TOPIC_ARN"] = "arn:aws:sns:ap-southeast-2:123456789012:feedback-alerts"
    try:
        result = lf.lambda_handler(event_with(name="A", rollno="11", rating="4", comment="ok"), None)
    finally:
        del os.environ["SNS_TOPIC_ARN"]

    assert result["statusCode"] == 200
    assert table.get_item(Key={"rollno": "11"})["Item"]["rating"] == "4"
