"""
Craft Docs API client for creating and updating documents.

The Craft API uses a block-based structure where content is inserted via
the /blocks endpoint with position parameters specifying the target document.
"""

from typing import Any, Optional
import httpx

from .config import CraftConfig


class CraftAPIError(Exception):
    """
    Exception raised for Craft API errors.
    """

    def __init__(self, message: str, status_code: Optional[int] = None):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


class CraftClient:
    """
    Client for interacting with the Craft Docs API.

    The Craft API works with blocks rather than documents directly.
    Content is inserted into existing documents using the /blocks endpoint.
    """

    def __init__(self, config: CraftConfig):
        """
        Initialize the Craft client.

        Args:
            config: CraftConfig instance with API URL and settings.
        """
        self.config = config
        self.base_url = config.api_url.rstrip("/")
        self._client: Optional[httpx.Client] = None

    def _get_headers(self) -> dict[str, str]:
        """
        Build request headers, including API key if configured.
        """
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key.get_secret_value()}"
        return headers

    @property
    def client(self) -> httpx.Client:
        """
        Get or create the HTTP client.
        """
        if self._client is None:
            self._client = httpx.Client(
                timeout=120.0,  # Increased timeout for large syncs
                headers=self._get_headers(),
            )
        return self._client

    def _handle_response(self, response: httpx.Response) -> dict[str, Any]:
        """
        Handle API response, raising errors if necessary.
        """
        if response.status_code >= 400:
            try:
                error_data = response.json()
                message = error_data.get("error", error_data.get("message", response.text))
            except Exception:
                message = response.text or f"HTTP {response.status_code}"
            raise CraftAPIError(message, response.status_code)

        try:
            return response.json()
        except Exception:
            return {"status": "ok"}

    def get_documents(self) -> list[dict[str, Any]]:
        """
        Get all documents accessible via the API.

        Returns:
            List of document data dictionaries with id, title, isDeleted.
        """
        response = self.client.get(f"{self.base_url}/documents")
        result = self._handle_response(response)
        return result.get("items", [])

    def get_block(self, block_id: str) -> dict[str, Any]:
        """
        Get a block (document or content block) by ID.

        Args:
            block_id: The block/document ID.

        Returns:
            Block data including id, type, markdown, and content.
        """
        response = self.client.get(f"{self.base_url}/blocks", params={"id": block_id})
        return self._handle_response(response)

    def insert_markdown(
        self,
        markdown: str,
        page_id: str,
        position: str = "end",
    ) -> list[dict[str, Any]]:
        """
        Insert markdown content into a document.

        Args:
            markdown: Markdown content to insert.
            page_id: ID of the page/document to insert into.
            position: Where to insert - "start" or "end".

        Returns:
            List of created block items with their IDs.
        """
        payload = {
            "markdown": markdown,
            "position": {
                "position": position,
                "pageId": page_id,
            }
        }
        response = self.client.post(f"{self.base_url}/blocks", json=payload)
        result = self._handle_response(response)
        return result.get("items", [])

    def insert_blocks(
        self,
        blocks: list[dict[str, Any]],
        page_id: str,
        position: str = "end",
    ) -> list[dict[str, Any]]:
        """
        Insert structured blocks into a document.

        Args:
            blocks: List of block objects with type, markdown, etc.
            page_id: ID of the page/document to insert into.
            position: Where to insert - "start" or "end".

        Returns:
            List of created block items with their IDs.
        """
        payload = {
            "blocks": blocks,
            "position": {
                "position": position,
                "pageId": page_id,
            }
        }
        response = self.client.post(f"{self.base_url}/blocks", json=payload)
        result = self._handle_response(response)
        return result.get("items", [])

    def update_blocks(self, blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Update existing blocks.

        Args:
            blocks: List of block objects with id and updated content.

        Returns:
            List of updated block items.
        """
        payload = {"blocks": blocks}
        response = self.client.put(f"{self.base_url}/blocks", json=payload)
        result = self._handle_response(response)
        return result.get("items", [])

    def delete_blocks(self, block_ids: list[str]) -> dict[str, Any]:
        """
        Delete blocks by ID.

        Args:
            block_ids: List of block IDs to delete.

        Returns:
            Deletion confirmation.
        """
        payload = {"blockIds": block_ids}
        # httpx delete doesn't support json body, use request directly
        response = self.client.request("DELETE", f"{self.base_url}/blocks", json=payload)
        return self._handle_response(response)

    def clear_document(self, page_id: str) -> None:
        """
        Clear all content from a document.

        Args:
            page_id: ID of the page/document to clear.
        """
        block = self.get_block(page_id)
        content = block.get("content", [])

        if content:
            block_ids = [item.get("id") for item in content if item.get("id")]
            if block_ids:
                self.delete_blocks(block_ids)

    def search_blocks(self, query: str, page_id: Optional[str] = None) -> list[dict[str, Any]]:
        """
        Search for blocks containing text.

        Args:
            query: Search query.
            page_id: Optional page ID to search within.

        Returns:
            List of matching blocks.
        """
        params: dict[str, str] = {"q": query}
        if page_id:
            params["pageId"] = page_id

        response = self.client.get(f"{self.base_url}/blocks/search", params=params)
        result = self._handle_response(response)
        return result.get("items", [])

    def test_connection(self) -> bool:
        """
        Test the connection to the Craft API.

        Returns:
            True if connection successful, False otherwise.
        """
        try:
            self.get_documents()
            return True
        except Exception:
            return False

    def close(self) -> None:
        """
        Close the HTTP client.
        """
        if self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self) -> "CraftClient":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()


class MarkdownBuilder:
    """
    Helper class for building markdown content for Craft.

    Craft accepts markdown and converts it to blocks automatically.
    """

    @staticmethod
    def heading(text: str, level: int = 1) -> str:
        """
        Create a heading.
        """
        prefix = "#" * min(max(level, 1), 6)
        return f"{prefix} {text}"

    @staticmethod
    def bullet_list(items: list[str]) -> str:
        """
        Create a bullet list.
        """
        return "\n".join(f"- {item}" for item in items)

    @staticmethod
    def numbered_list(items: list[str]) -> str:
        """
        Create a numbered list.
        """
        return "\n".join(f"{i+1}. {item}" for i, item in enumerate(items))

    @staticmethod
    def bold(text: str) -> str:
        """
        Make text bold.
        """
        return f"**{text}**"

    @staticmethod
    def italic(text: str) -> str:
        """
        Make text italic.
        """
        return f"*{text}*"

    @staticmethod
    def code_block(code: str, language: str = "") -> str:
        """
        Create a code block.
        """
        return f"```{language}\n{code}\n```"

    @staticmethod
    def horizontal_rule() -> str:
        """
        Create a horizontal rule.
        """
        return "---"

    @staticmethod
    def key_value(key: str, value: str) -> str:
        """
        Create a key-value pair with bold key.
        """
        return f"**{key}:** {value}"

    @staticmethod
    def status_badge(status: str) -> str:
        """
        Create a status indicator string.
        """
        status_icons = {
            "running": "🟢",
            "stopped": "🔴",
            "paused": "🟡",
            "suspended": "🟠",
            "unknown": "⚪",
        }
        icon = status_icons.get(status.lower(), "⚪")
        return f"{icon} {status.capitalize()}"

    @staticmethod
    def table(headers: list[str], rows: list[list[str]]) -> str:
        """
        Create a markdown table.
        """
        lines = []
        lines.append("| " + " | ".join(headers) + " |")
        lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
        for row in rows:
            lines.append("| " + " | ".join(row) + " |")
        return "\n".join(lines)
