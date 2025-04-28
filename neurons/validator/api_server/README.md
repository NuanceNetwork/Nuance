# Nuance Network API

## For Users

The Nuance Network API provides access to the validator's knowledge and services, allowing you to check post verification status, account verification, and text nuance evaluation.

### Available Endpoints

#### Nuance Checking

- **POST `/nuance/check`**
  - Check if your text meets our nuance criteria
  - Rate limited to 2 requests per minute per IP
  - Request format: `{"text": "Your text to analyze"}`
  - Returns whether text is considered nuanced

#### Account Verification

- **GET `/accounts/verify/{platform_type}/{account_id}`**
  - Check if a social media account is verified in the Nuance Network
  - Example: `/accounts/verify/twitter/12345`
  - Returns verification status and associated miner information (if verified)

#### Post Management

- **GET `/posts/{platform_type}/{post_id}`**
  - Get verification status and interaction information for a specific post
  - Example: `/posts/twitter/1234567890`
  - Returns post processing status and interaction count

- **GET `/posts/{platform_type}/{post_id}/interactions`**
  - Get paginated list of interactions for a specific post
  - Parameters: `skip`, `limit` (defaults to 0 and 20)
  - Example: `/posts/twitter/1234567890/interactions?skip=0&limit=20`
  - Returns interactions sorted by recency

#### Interaction Management

- **GET `/interactions/{platform_type}/{interaction_id}`**
  - Get details for a specific interaction
  - Example: `/interactions/twitter/9876543210`
  - Returns interaction type, content, and processing status

#### Miner Statistics

- **GET `/miners/{hotkey}/stats`**
  - Get overall statistics for a miner
  - Example: `/miners/5FHneW46xGXgs5mUiveU4sbTyGBzmstUspZC92UhjJM694ty/stats`
  - Returns account count, post count, and interaction count

- **GET `/miners/{hotkey}/posts`**
  - Get posts submitted by a miner with pagination
  - Parameters: `skip`, `limit` (defaults to 0 and 20)
  - Example: `/miners/5FHneW46xGXgs5mUiveU4sbTyGBzmstUspZC92UhjJM694ty/posts?skip=0&limit=20`
  - Returns posts sorted by recency

### Using the API

#### Interactive Documentation
Access the beautiful, interactive API documentation at `/scalar` (or simply visit the root URL `/`).

#### Example API Requests

Check if text meets nuance criteria:
```bash
curl -X POST "http://localhost:8000/nuance/check" \
  -H "Content-Type: application/json" \
  -d '{"text": "While AI may displace some jobs, it could also create new opportunities in different sectors. The impact varies by industry, timeframe, and implementation approach."}'
```

Verify an account:
```bash
curl -X GET "http://localhost:8000/accounts/verify/twitter/12345"
```

Get interactions for a post:
```bash
curl -X GET "http://localhost:8000/posts/twitter/1234567890/interactions?skip=0&limit=10"
```

#### Rate Limits
- Nuance checking endpoint: 2 requests per minute per IP address
- All other endpoints: Currently unlimited

## For Developers

### API Architecture

The Nuance Network API is built with FastAPI, providing:
- Asynchronous request handling
- Automatic Swagger and OpenAPI documentation
- Integration with Scalar for enhanced API documentation
- Rate limiting via SlowAPI
- Comprehensive request logging

### Response Models

The API uses Pydantic models for type-safe request and response handling:

#### `PostVerificationResponse`
```python
class PostVerificationResponse(BaseModel):
    platform_type: str
    post_id: str
    content: str
    topics: List[str] = []
    processing_status: str
    processing_note: Optional[str] = None
    interaction_count: int = 0
```

#### `InteractionResponse`
```python
class InteractionResponse(BaseModel):
    platform_type: str
    interaction_id: str
    interaction_type: str
    post_id: str
    account_id: str
    content: Optional[str] = None
    processing_status: str
    processing_note: Optional[str] = None
```

#### `AccountVerificationResponse`
```python
class AccountVerificationResponse(BaseModel):
    platform_type: str
    account_id: str
    username: str
    node_hotkey: Optional[str] = None
    node_netuid: Optional[int] = None
    is_verified: bool
```

### Running the API Server

To start the API server:

```bash
# Install required dependencies
pip install -e ".[api]"

# Run the server
python -m neurons.validator.api_server
```

By default, the server will run on port 8000 and will be accessible at `http://localhost:8000`.

### Dependency Injection

The API uses FastAPI's dependency injection system to provide repositories and services:

```python
@app.get("/posts/{platform_type}/{post_id}")
async def get_post(
    platform_type: str,
    post_id: str,
    post_repo: Annotated[PostRepository, Depends(get_post_repo)],
    interaction_repo: Annotated[InteractionRepository, Depends(get_interaction_repo)],
):
    # Implementation...
```

This makes the code more testable and maintainable.

### Logging

The API server implements comprehensive logging:
- Request/response logging via middleware
- Detailed endpoint logging
- Error logging with stack traces
- Rate limit violation logging

### Adding New Endpoints

To add a new endpoint:
1. Define any new response/request models in `neurons/validator/api_server/models.py`
2. Add necessary dependencies in `neurons/validator/api_server/dependencies.py`
3. Implement the endpoint in `neurons/validator/api_server.py`
4. Add documentation and examples to this README

### Error Handling

The API implements consistent error handling:
- 404 responses for not found resources
- 500 responses for internal errors
- Rate limit exceeded responses (429)
- Custom error details