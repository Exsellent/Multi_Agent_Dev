import logging
import os
from typing import Dict, Any, List

import httpx

logger = logging.getLogger("jira_client")


class JiraClient:
    def __init__(self):
        self.url = os.getenv("JIRA_URL", "").rstrip("/")
        self.email = os.getenv("JIRA_EMAIL")
        self.token = os.getenv("JIRA_API_TOKEN")
        self.project_key = os.getenv("JIRA_PROJECT_KEY", "PROJ")

        if not all([self.url, self.email, self.token]):
            logger.warning("⚠️ JIRA credentials not set — using MOCK mode")
            self.mock_mode = True
        else:
            logger.info(f"✅ JIRA client initialized for {self.url}")
            self.mock_mode = False

    async def create_task(
            self,
            summary: str,
            description: str,
            issue_type: str = "Task"
    ) -> Dict[str, Any]:
        """Create Jira issue"""

        logger.info("Creating Jira task", extra={
            "summary": summary[:50],
            "mode": "mock" if self.mock_mode else "real"
        })

        if self.mock_mode:
            # Mock response для демо
            mock_key = f"{self.project_key}-{hash(summary) % 1000}"
            return {
                "status": "mock_created",
                "issue_key": mock_key,
                "url": f"https://mock-jira.atlassian.net/browse/{mock_key}",
                "mock": True
            }

        # Real Jira API call
        auth = httpx.BasicAuth(self.email, self.token)

        # Jira Cloud API v3 format
        payload = {
            "fields": {
                "project": {"key": self.project_key},
                "summary": summary,
                "description": {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [
                                {
                                    "type": "text",
                                    "text": description
                                }
                            ]
                        }
                    ]
                },
                "issuetype": {"name": issue_type}
            }
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    f"{self.url}/rest/api/3/issue",
                    auth=auth,
                    json=payload,
                    headers={"Content-Type": "application/json"}
                )
                resp.raise_for_status()
                data = resp.json()

                issue_key = data["key"]

                logger.info("✅ Jira task created", extra={"issue_key": issue_key})

                return {
                    "status": "created",
                    "issue_key": issue_key,
                    "url": f"{self.url}/browse/{issue_key}",
                    "id": data.get("id"),
                    "mock": False
                }

        except httpx.HTTPStatusError as e:
            logger.error("❌ Jira API error", extra={
                "status": e.response.status_code,
                "error": e.response.text
            })
            return {
                "status": "error",
                "error": f"HTTP {e.response.status_code}: {e.response.text[:200]}",
                "mock": False
            }
        except Exception as e:
            logger.error("❌ Jira creation failed", extra={"error": str(e)})
            return {
                "status": "error",
                "error": str(e),
                "mock": False
            }

    async def get_project_issues(self, max_results: int = 50) -> List[Dict]:
        """Get all issues from project"""

        if self.mock_mode:

            return [
                {
                    "key": f"{self.project_key}-1",
                    "fields": {
                        "summary": "Implement authentication",
                        "status": {"name": "Done"}
                    }
                },
                {
                    "key": f"{self.project_key}-2",
                    "fields": {
                        "summary": "Add API documentation",
                        "status": {"name": "In Progress"}
                    }
                },
                {
                    "key": f"{self.project_key}-3",
                    "fields": {
                        "summary": "Setup CI/CD",
                        "status": {"name": "To Do"}
                    }
                }
            ]

        auth = httpx.BasicAuth(self.email, self.token)

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    f"{self.url}/rest/api/3/search",
                    auth=auth,
                    params={
                        "jql": f"project={self.project_key}",
                        "maxResults": max_results,
                        "fields": "summary,status,assignee,created"
                    }
                )
                resp.raise_for_status()
                data = resp.json()

                return data.get("issues", [])

        except Exception as e:
            logger.error("Failed to fetch Jira issues", extra={"error": str(e)})
            return []
