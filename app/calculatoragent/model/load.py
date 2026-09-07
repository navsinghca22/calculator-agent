from strands.models.bedrock import BedrockModel


def load_model() -> BedrockModel:
    """Get Bedrock model client using IAM credentials."""
    return BedrockModel(
    model_id="us.amazon.nova-2-lite-v1:0",
    # Cost summaries need enough room to report the services, date range, and
    # estimated-status disclosure without being cut off mid-response.
    max_tokens=256,
)
