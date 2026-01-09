"""Database service for SQLite operations and data import.

This service provides two categories of methods:
1. Initialization methods: Used when the agent starts to set up the database
2. Workflow query methods: Used during the agentic workflow to find data
"""

from contextlib import closing
from pathlib import Path
from sqlite3 import connect
from typing import Any, Optional, Union

import pandas as pd

from agent.configuration import Configuration


class DatabaseService:
    """Service for interacting with SQLite database.
    
    Provides methods for:
    - Database initialization and data import (used at agent startup)
    - Querying customer data during workflow execution
    """
    
    def __init__(self, config: Configuration):
        """Initialize database service with configuration.
        
        Args:
            config: Configuration object containing database settings
            
        Note:
            Creates the database directory if it doesn't exist.
        """
        self.config = config
        self.database_path = Path(config.database_path)
        
        # Create database directory if it doesn't exist
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
    
    # ============================================================================
    # PRIVATE HELPER METHODS
    # ============================================================================
    
    def _get_connection(self):
        """Get a database connection.
        
        Returns:
            SQLite connection object
        """
        return connect(str(self.database_path))
    
    # ============================================================================
    # INITIALIZATION METHODS
    # Used when the agent starts to set up the database
    # ============================================================================
    
    def import_from_json(self, table_name: str, json_file_path: Union[str, Path]) -> int:
        """Import JSON data into a database table.
        
        Creates or replaces the table with data from the JSON file.
        Used during agent initialization to populate the database.
        
        Args:
            table_name: Name of the table to create/update
            json_file_path: Path to the JSON file containing the data
            
        Returns:
            Number of rows imported
            
        Raises:
            FileNotFoundError: If JSON file doesn't exist
            ValueError: If JSON file is invalid
            Exception: If import fails
        """
        json_path = Path(json_file_path)
        if not json_path.exists():
            raise FileNotFoundError(f"JSON file not found: {json_file_path}")
        
        try:
            # Read JSON file into pandas DataFrame
            df = pd.read_json(json_path)
            
            if df.empty:
                print(f"Warning: JSON file {json_file_path} is empty")
                return 0
            
            # Import into SQLite database
            with closing(self._get_connection()) as conn:
                df.to_sql(table_name, conn, if_exists='replace', index=False)
                row_count = len(df)
            
            print(f"Imported {row_count} rows into table '{table_name}' from {json_file_path}")
            return row_count
        except pd.errors.EmptyDataError:
            raise ValueError(f"JSON file is empty or invalid: {json_file_path}")
        except Exception as e:
            error_msg = f"Error importing table {table_name} from {json_file_path}: {str(e)}"
            print(f"ERROR: {error_msg}")
            raise Exception(error_msg) from e
    
    def initialize(self, data_path: Optional[Union[str, Path]] = None) -> dict[str, Any]:
        """Initialize database with all sample data tables from JSON files.
        
        Imports customers, orders, transactions, and refunds tables.
        This method should be called when the agent starts to set up the database.
        
        Args:
            data_path: Optional path to data directory. If None, uses project data folder.
            
        Returns:
            Dictionary with import results for each table
            
        Raises:
            FileNotFoundError: If data directory doesn't exist
        """
        # Determine data path
        if data_path is None:
            # Get project root (assuming database.py is in src/services/)
            project_root = Path(__file__).parent.parent.parent
            data_path = project_root / "data"
        else:
            data_path = Path(data_path)
        
        if not data_path.exists():
            raise FileNotFoundError(f"Data directory not found: {data_path}")
        
        results: dict[str, Any] = {}
        tables = ['customers', 'orders', 'transactions', 'refunds']
        
        for table_name in tables:
            json_file = data_path / f"{table_name}.json"
            try:
                row_count = self.import_from_json(table_name, json_file)
                results[table_name] = {
                    "status": "SUCCESS",
                    "rows_imported": row_count,
                    "source_file": str(json_file)
                }
            except FileNotFoundError:
                results[table_name] = {
                    "status": "SKIPPED",
                    "reason": f"JSON file not found: {json_file}"
                }
            except Exception as e:
                results[table_name] = {
                    "status": "ERROR",
                    "error": str(e)
                }
        
        return results
    
    def table_exists(self, table_name: str) -> bool:
        """Check if a table exists in the database.
        
        Useful for verifying database initialization.
        
        Args:
            table_name: Name of the table to check
            
        Returns:
            True if table exists, False otherwise
        """
        try:
            sql = "SELECT name FROM sqlite_master WHERE type='table' AND name=?"
            results = self.query(sql, params=[table_name])
            return len(results) > 0
        except Exception:
            return False
    
    def get_table_info(self, table_name: str) -> dict[str, Any]:
        """Get information about a table including row count and column names.
        
        Useful for verifying database initialization and debugging.
        
        Args:
            table_name: Name of the table
            
        Returns:
            Dictionary with table information (exists, row_count, columns)
        """
        info: dict[str, Any] = {
            "exists": False,
            "row_count": 0,
            "columns": []
        }
        
        if not self.table_exists(table_name):
            return info
        
        info["exists"] = True
        
        try:
            # Get row count
            count_results = self.query(f"SELECT COUNT(*) as count FROM {table_name}")
            if count_results:
                info["row_count"] = count_results[0].get("count", 0)
            
            # Get column names
            sql = f"PRAGMA table_info({table_name})"
            pragma_results = self.query(sql)
            info["columns"] = [col.get("name", "") for col in pragma_results]
        except Exception as e:
            print(f"Warning: Could not get table info for {table_name}: {str(e)}")
        
        return info
    
    # ============================================================================
    # WORKFLOW QUERY METHODS
    # Used during the agentic workflow to find customer data
    # ============================================================================
    
    def query(self, sql: str, params: Optional[list] = None) -> list[dict[str, Any]]:
        """Execute a SQL query and return results as a list of dictionaries.
        
        General-purpose query method used by workflow methods.
        Supports parameterized queries for SQL injection prevention.
        
        Args:
            sql: SQL query string (supports parameterized queries with ?)
            params: Optional list of parameters for parameterized queries
            
        Returns:
            List of dictionaries, where each dict represents a row
            
        Raises:
            Exception: If query execution fails
        """
        try:
            with closing(self._get_connection()) as conn:
                df = pd.read_sql_query(sql=sql, con=conn, params=params)
            
            # Convert DataFrame to list of dicts
            if not df.empty:
                return df.to_dict(orient='records')
            else:
                return []
        except Exception as e:
            error_msg = f"Error executing query: {str(e)}"
            print(f"ERROR: {error_msg}")
            raise Exception(error_msg) from e
    
    def find_order(self, order_no: str) -> Optional[dict[str, Any]]:
        """Find an order by order number.
        
        Used during workflow execution to retrieve order details.
        
        Args:
            order_no: Order number to search for
            
        Returns:
            Order dictionary if found, None otherwise
        """
        sql = "SELECT * FROM orders WHERE order_no = ? LIMIT 1"
        results = self.query(sql, params=[order_no])
        return results[0] if results else None
    
    def find_transaction(self, transaction_id: str) -> Optional[dict[str, Any]]:
        """Find a transaction by transaction ID.
        
        Used during workflow execution to retrieve transaction details.
        
        Args:
            transaction_id: Transaction ID to search for
            
        Returns:
            Transaction dictionary if found, None otherwise
        """
        sql = "SELECT * FROM transactions WHERE transaction_id = ? LIMIT 1"
        results = self.query(sql, params=[transaction_id])
        return results[0] if results else None
    
    def find_refund(self, refund_id: str) -> Optional[dict[str, Any]]:
        """Find a refund by refund ID.
        
        Used during workflow execution to retrieve refund status.
        
        Args:
            refund_id: Refund ID to search for
            
        Returns:
            Refund dictionary if found, None otherwise
        """
        sql = "SELECT * FROM refunds WHERE refund_id = ? LIMIT 1"
        results = self.query(sql, params=[refund_id])
        return results[0] if results else None
    
    def get_transaction_for_order(self, order_no: str) -> Optional[dict[str, Any]]:
        """Get transaction information for an order.
        
        Args:
            order_no: Order number to search for
            
        Returns:
            Transaction dictionary if found, None otherwise
        """
        sql = "SELECT * FROM transactions WHERE order_no = ? LIMIT 1"
        results = self.query(sql, params=[order_no])
        return results[0] if results else None
    
    def get_refund_for_order(self, order_no: str) -> Optional[dict[str, Any]]:
        """Get refund information for an order.
        
        Args:
            order_no: Order number to search for
            
        Returns:
            Refund dictionary if found, None otherwise
        """
        sql = "SELECT * FROM refunds WHERE order_no = ? LIMIT 1"
        results = self.query(sql, params=[order_no])
        return results[0] if results else None
    
    def find_customer(self, customer_id: Optional[str] = None, email: Optional[str] = None) -> Optional[dict[str, Any]]:
        """Find a customer by customer ID or email.
        
        Used during workflow execution to retrieve customer information.
        
        Args:
            customer_id: Customer ID to search for (optional)
            email: Email address to search for (optional)
            
        Returns:
            Customer dictionary if found, None otherwise
            
        Raises:
            ValueError: If neither customer_id nor email is provided
        """
        if not customer_id and not email:
            raise ValueError("Either customer_id or email must be provided")
        
        if customer_id:
            sql = "SELECT * FROM customers WHERE customer_id = ? LIMIT 1"
            params = [customer_id]
        else:
            sql = "SELECT * FROM customers WHERE email = ? LIMIT 1"
            params = [email]
        
        results = self.query(sql, params=params)
        return results[0] if results else None
    
