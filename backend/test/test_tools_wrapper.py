import asyncio
import base64
import unittest
from unittest.mock import patch, MagicMock, AsyncMock

import pytest
from aiohttp import ClientResponseError, ClientConnectionError # Import ClientConnectionError
import sys
import os

# Add backend directory to sys.path to allow direct import of tools_wrapper
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from tools_wrapper import download_attachment

# Test data
VALID_B64_DATA = base64.urlsafe_b64encode(b"Hello, world!").decode('ascii')
MALFORMED_B64_DATA = "this is not base64"

@pytest.mark.asyncio
async def test_download_attachment_success():
    mock_session_get = AsyncMock()
    mock_response = mock_session_get.return_value.__aenter__.return_value
    mock_response.status = 200
    mock_response.json = AsyncMock(return_value={'data': VALID_B64_DATA})
    mock_response.raise_for_status = MagicMock()

    with patch('aiohttp.ClientSession.get', mock_session_get):
        result = await download_attachment('me', 'msg_id', 'att_id', 'fake_token')
        assert result == b"Hello, world!"
        mock_session_get.assert_called_once_with(
            "https://www.googleapis.com/gmail/v1/users/me/messages/msg_id/attachments/att_id",
            headers={"Authorization": "Bearer fake_token", "Accept": "application/json"}
        )

@pytest.mark.asyncio
async def test_download_attachment_api_404():
    mock_session_get = AsyncMock()
    mock_response = mock_session_get.return_value.__aenter__.return_value
    mock_response.status = 404
    mock_response.raise_for_status = MagicMock(side_effect=ClientResponseError(
        request_info=MagicMock(),
        history=MagicMock(),
        status=404,
        message="Not Found"
    ))
    mock_response.json = AsyncMock(return_value={'error': 'not found'})


    with patch('aiohttp.ClientSession.get', mock_session_get):
        with pytest.raises(ClientResponseError) as excinfo:
            await download_attachment('me', 'msg_id_404', 'att_id_404', 'fake_token')
        assert excinfo.value.status == 404

@pytest.mark.asyncio
async def test_download_attachment_api_401():
    mock_session_get = AsyncMock()
    mock_response = mock_session_get.return_value.__aenter__.return_value
    mock_response.status = 401
    mock_response.raise_for_status = MagicMock(side_effect=ClientResponseError(
        request_info=MagicMock(),
        history=MagicMock(),
        status=401,
        message="Unauthorized"
    ))
    mock_response.json = AsyncMock(return_value={'error': 'unauthorized'})


    with patch('aiohttp.ClientSession.get', mock_session_get):
        with pytest.raises(ClientResponseError) as excinfo:
            await download_attachment('me', 'msg_id_401', 'att_id_401', 'fake_token')
        assert excinfo.value.status == 401

@pytest.mark.asyncio
async def test_download_attachment_missing_data_field():
    mock_session_get = AsyncMock()
    mock_response = mock_session_get.return_value.__aenter__.return_value
    mock_response.status = 200
    mock_response.json = AsyncMock(return_value={'not_data': 'some_value'}) # 'data' field missing
    mock_response.raise_for_status = MagicMock()

    with patch('aiohttp.ClientSession.get', mock_session_get):
        with pytest.raises(ValueError) as excinfo:
            await download_attachment('me', 'msg_id_no_data', 'att_id_no_data', 'fake_token')
        assert "Attachment data field missing" in str(excinfo.value)

@pytest.mark.asyncio
async def test_download_attachment_malformed_base64():
    mock_session_get = AsyncMock()
    mock_response = mock_session_get.return_value.__aenter__.return_value
    mock_response.status = 200
    mock_response.json = AsyncMock(return_value={'data': MALFORMED_B64_DATA})
    mock_response.raise_for_status = MagicMock()

    with patch('aiohttp.ClientSession.get', mock_session_get):
        with pytest.raises(ValueError) as excinfo:
            await download_attachment('me', 'msg_id_bad_b64', 'att_id_bad_b64', 'fake_token')
        assert "Base64 decoding failed" in str(excinfo.value)

@pytest.mark.asyncio
async def test_download_attachment_network_error():
    mock_session_get = AsyncMock(side_effect=ClientConnectionError("Simulated network error"))

    with patch('aiohttp.ClientSession.get', mock_session_get):
        with pytest.raises(ClientConnectionError):
            await download_attachment('me', 'msg_id_network_error', 'att_id_network_error', 'fake_token')

# This allows running the tests with `python backend/test/test_tools_wrapper.py`
if __name__ == '__main__':
    # A simple way to run pytest tests, or use `pytest` command in terminal
    pytest.main([__file__])
