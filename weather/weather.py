from typing import Any
import hashlib
from loguru import logger
from mcp.server.fastmcp import FastMCP

# Initialize FastMCP server
mcp = FastMCP("public-demo")

@mcp.tool()
def generate_md5_hash(input_str: str) -> str:
    # Create an md5 hash object
    logger.info(f"Generating MD5 hash for: {input_str}")
    md5_hash = hashlib.md5()
    
    # Update the hash object with the bytes of the input string
    md5_hash.update(input_str.encode('utf-8'))
    
    # Return the hexadecimal representation of the digest
    return md5_hash.hexdigest()

@mcp.tool()
def count_characters(input_str: str) -> int:
    # Count number of characters in the input string
    logger.info(f"Counting characters in: {input_str}")
    return len(input_str)


@mcp.tool()
def get_first_half(input_str: str) -> str:
    # Calculate the midpoint of the string
    logger.info(f"Getting first half of: {input_str}")
    midpoint = len(input_str) // 2
    
    # Return the first half of the string
    return input_str[:midpoint]


if __name__ == "__main__":
    # Initialize and run the server
    mcp.run(transport='stdio')