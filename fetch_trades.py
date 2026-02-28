#!/usr/bin/env python3
"""
Simple script to fetch and save Polymarket trades for a user and market.
"""

import sys
import json
import requests
from typing import Optional, Tuple

SEARCH_URL = "https://gamma-api.polymarket.com/public-search"
TRADES_URL = "https://data-api.polymarket.com/trades"
DEFAULT_OUTPUT_FILE = "trades.json"


def search_markets(query: str) -> Tuple[Optional[dict], list]:
    """Search for an event and return (event, list_of_markets) tuple."""
    try:
        resp = requests.get(SEARCH_URL, params={"q": query}, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as exc:
        print(f"Error searching markets: {exc}", file=sys.stderr)
        return None, []

    events = data.get("events", []) if isinstance(data, dict) else []
    for event in events:
        markets = event.get("markets") or []
        if markets:
            return event, markets
    return None, []


def verify_all_trades_fetched(condition_id: str, user_address: str, fetched_count: int, page_limit: int = 5000) -> bool:
    """Verify that we fetched all trades by checking if there are more beyond our last fetch."""
    # Check one page beyond what we fetched
    test_offset = fetched_count
    params = {
        "limit": page_limit,
        "offset": test_offset,
        "takerOnly": "false",
        "market": condition_id,
        "user": user_address,
    }
    try:
        resp = requests.get(TRADES_URL, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        
        if isinstance(data, dict):
            batch = data.get("trades", [])
        elif isinstance(data, list):
            batch = data
        else:
            batch = []
        
        return len(batch) == 0
    except requests.RequestException:
        return True  # Assume OK if we can't verify


def fetch_trades(condition_id: str, user_address: str, page_limit: int = 5000) -> list:
    """Fetch all trades for a condition/user with pagination."""
    all_trades = []
    offset = 0
    page_num = 1

    print(f"Fetching trades for condition {condition_id} and user {user_address}...")
    
    while True:
        params = {
            "limit": page_limit,
            "offset": offset,
            "takerOnly": "false",
            "market": condition_id,
            "user": user_address,
        }
        try:
            resp = requests.get(TRADES_URL, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as exc:
            print(f"Error fetching trades: {exc}", file=sys.stderr)
            return []

        if isinstance(data, dict):
            batch = data.get("trades", [])
            # Check if there's a total count in the response
            total_count = data.get("totalCount") or data.get("total")
            if total_count is not None:
                print(f"  API reports total count: {total_count}")
        elif isinstance(data, list):
            batch = data
        else:
            batch = []

        all_trades.extend(batch)
        print(f"  Page {page_num} (offset {offset}): Fetched {len(batch)} trades (total so far: {len(all_trades)})")
        
        # Stop if we got fewer trades than requested (means we're at the end)
        if len(batch) < page_limit:
            print(f"  Reached end of results (got {len(batch)} < {page_limit} trades)")
            break
        
        # Safety check: if we got exactly page_limit trades, continue
        offset += page_limit
        page_num += 1
        
        # Safety limit to prevent infinite loops
        if page_num > 1000:
            print(f"  Warning: Reached safety limit of 1000 pages. Stopping.")
            break

    # Verify we got everything if API provided a total count
    if isinstance(data, dict):
        total_count = data.get("totalCount") or data.get("total")
        if total_count is not None and len(all_trades) != total_count:
            print(f"  Warning: Expected {total_count} trades but fetched {len(all_trades)}")
    
    return all_trades


def main():
    """Main function to fetch and save trades."""
    # Parse command line arguments
    if len(sys.argv) < 3:
        print("Usage: python fetch_trades.py <market_query> <user_address> [output_file]")
        print("\nExample:")
        print("  python fetch_trades.py 'Will Trump win?' 0x1234... trades.json")
        sys.exit(1)

    market_query = sys.argv[1]
    user_address = sys.argv[2]
    output_file = sys.argv[3] if len(sys.argv) > 3 else DEFAULT_OUTPUT_FILE

    # Search for event and its markets
    print(f"Searching for event: {market_query}")
    event, markets = search_markets(market_query)
    
    if not event or not markets:
        print("Error: No market found for that query.", file=sys.stderr)
        sys.exit(1)

    print(f"\nFound event: {event.get('title', 'Unknown Event')}")
    print(f"Found {len(markets)} sub-markets under this event. Fetching trades for all of them...\n")

    all_trades = []
    
    for idx, market in enumerate(markets):
        market_title = (
            market.get("question")
            or market.get("title")
            or event.get("title", "Unknown Market")
        )
        condition_id = market.get("conditionId") or ""
        
        if not condition_id:
            continue
            
        print(f"--- Market {idx+1}/{len(markets)}: {market_title} ---")
        print(f"Condition ID: {condition_id}")

        # Fetch trades
        trades = fetch_trades(condition_id, user_address)
        
        if trades:
            if verify_all_trades_fetched(condition_id, user_address, len(trades)):
                print("  [OK] Verification passed: All trades fetched.")
            else:
                print("  [!] Warning: Additional trades may exist.")
            all_trades.extend(trades)
        else:
            print("  No trades found in this sub-market.")
        print()
    
    if not all_trades:
        print("No trades found for that user across all markets in this event.")
        sys.exit(0)

    # Sort by timestamp
    all_trades.sort(key=lambda x: x.get("timestamp", 0))

    # Save to file
    try:
        with open(output_file, "w") as f:
            json.dump(all_trades, f, indent=2)
        print(f"Successfully saved {len(all_trades)} total trades to {output_file}")
    except IOError as exc:
        print(f"Error writing to file: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
