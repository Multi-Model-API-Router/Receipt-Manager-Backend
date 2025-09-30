from rest_framework.response import Response
from rest_framework import status
from typing import Any, Dict, Optional

def success_response(
    message: str = "Success",
    data: Any = None,
    status_code: int = status.HTTP_200_OK,
    headers: Optional[Dict[str, str]] = None
) -> Response:
    """
    Standardized success response format
    """
    response_data = {
        "message": message,
        "data": data,
        "status": status_code
    }
    
    return Response(response_data, status=status_code, headers=headers)

def paginated_response(
    message: str = "Success",
    data: Any = None,
    pagination_data: Dict[str, Any] = None,
    status_code: int = status.HTTP_200_OK
) -> Response:
    """
    Standardized paginated response format
    """
    response_data = {
        "message": message,
        "data": data,
        "pagination": pagination_data or {},
        "status": status_code
    }
    
    return Response(response_data, status=status_code)

def created_response(
    message: str = "Created successfully",
    data: Any = None,
    headers: Optional[Dict[str, str]] = None
) -> Response:
    """
    Standardized creation response
    """
    return success_response(
        message=message,
        data=data,
        status_code=status.HTTP_201_CREATED,
        headers=headers
    )

def no_content_response(message: str = "Operation completed successfully") -> Response:
    """
    Standardized no content response
    """
    return success_response(
        message=message,
        data=None,
        status_code=status.HTTP_204_NO_CONTENT
    )
