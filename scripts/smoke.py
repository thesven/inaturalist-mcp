"""Exercise installed-wheel stdio discovery without account credentials or network calls."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

import inaturalist_mcp

module = Path(inaturalist_mcp.__file__).resolve()
assert "site-packages" in module.parts, "Smoke test must execute against the installed wheel."


async def main() -> None:
    with tempfile.TemporaryDirectory() as directory:
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "inaturalist_mcp",
            "--transport",
            "stdio",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=directory,
            env={k: v for k, v in os.environ.items() if not k.startswith("INAT")},
        )

        try:
            assert process.stdin is not None
            assert process.stdout is not None

            # 1. Initialize handshake
            init_msg = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "smoke-test", "version": "1.0.0"},
                },
            }
            process.stdin.write((json.dumps(init_msg) + "\n").encode())
            await process.stdin.drain()

            init_response_raw = await asyncio.wait_for(process.stdout.readline(), timeout=10.0)
            init_response = json.loads(init_response_raw.decode())
            assert init_response.get("id") == 1, f"Bad init response: {init_response}"
            assert "error" not in init_response, f"Error in init response: {init_response}"
            assert init_response["result"]["serverInfo"]["name"] == "inaturalist"

            # 2. Initialized notification
            notify_msg = {"jsonrpc": "2.0", "method": "notifications/initialized"}
            process.stdin.write((json.dumps(notify_msg) + "\n").encode())
            await process.stdin.drain()

            # 3. List tools
            tools_msg = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
            process.stdin.write((json.dumps(tools_msg) + "\n").encode())
            await process.stdin.drain()

            tools_response_raw = await asyncio.wait_for(process.stdout.readline(), timeout=10.0)
            tools_response = json.loads(tools_response_raw.decode())
            assert tools_response.get("id") == 2, f"Bad tools response: {tools_response}"
            assert "error" not in tools_response, f"Error in tools response: {tools_response}"

            tools = tools_response["result"]["tools"]
            tool_names = {t["name"] for t in tools}
            expected_tools = {
                "observations_nearby",
                "taxon_observations_nearby",
                "rare_observations_nearby",
                "taxon_photo_evidence_nearby",
                "place_taxon_activity",
                "search_species",
                "get_taxon_details",
                "get_observation_details",
                "search_places",
                "get_nearby_places",
                "species_counts_nearby",
                "search_projects",
                "user_observations",
                "get_similar_species",
                "get_species_phenology",
                "get_controlled_terms",
                "view_observation_photos",
            }
            missing = expected_tools - tool_names
            assert expected_tools.issubset(tool_names), f"Missing tools: {missing}"
            assert len(tools) == 17, f"Expected 17 tools, found {len(tools)}"

            print(
                f"Installed wheel v{inaturalist_mcp.__version__}: "
                f"stdio handshake and all {len(tools)} tools verified successfully."
            )

        finally:
            if process.stdin:
                process.stdin.close()
            try:
                await asyncio.wait_for(process.wait(), timeout=3.0)
            except TimeoutError:
                process.kill()
                await process.wait()


if __name__ == "__main__":
    asyncio.run(main())
