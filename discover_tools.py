"""Quick script to discover available tools on the Arena MCP server."""
import asyncio, json, sys, io
from dotenv import load_dotenv
import os

# Force UTF-8 output
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

load_dotenv()

async def main():
    from fastmcp import Client
    endpoint = os.environ.get("MCP_ENDPOINT", "")
    print(f"Connecting to: {endpoint}")
    async with Client(endpoint) as client:
        tools = await client.list_tools()
        print(f"\n=== Found {len(tools)} tools ===\n")
        for t in tools:
            print(f"  Tool: {t.name}")
            print(f"  Description: {t.description}")
            schema = getattr(t, 'inputSchema', None) or getattr(t, 'input_schema', None)
            if schema:
                print(f"  Input Schema: {json.dumps(schema, indent=4)}")
            print()

asyncio.run(main())
