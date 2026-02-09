from fastapi import APIRouter
from fastapi.encoders import jsonable_encoder

# other imports

# Remove import for serialize_response
# from fastapi.routing import serialize_response

router = APIRouter()

# existing code

# changes around line 930

response = jsonable_encoder(response)

# existing code continues
