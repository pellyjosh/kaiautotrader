#!/usr/bin/env python3
"""
Enhanced Account Management CLI
Manage PocketOption trading accounts with Martingale settings
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.database_manager import DatabaseManager
import argparse
from typing import Optional

def display_accounts(dm: DatabaseManager, enabled_only: bool = False):
    """Display all accounts with their settings"""
    accounts = dm.get_enabled_accounts() if enabled_only else dm.get_all_accounts()
    
    if not accounts:
        print("No accounts found.")
        return
    
    print(f"\n{'='*90}")
    print(f"{'ACCOUNT MANAGEMENT' if not enabled_only else 'ENABLED ACCOUNTS'}")
    print(f"{'='*90}")
    
    header = f"{'Name':<20} {'SSID':<25} {'Demo':<6} {'Enabled':<8} {'Balance':<10} {'Base $':<8} {'Mult':<6} {'Mart':<6}"
    print(header)
    print("-" * 90)
    
    for acc in accounts:
        name = acc.get('worker_name', '')[:19]
        ssid = acc.get('ssid', '')[:24]
        is_demo = 'Yes' if acc.get('is_demo') else 'No'
        enabled = 'Yes' if acc.get('enabled') else 'No'
        balance = f"${acc.get('balance', 0):.2f}"
        base_amount = f"${acc.get('base_amount', 1.0):.2f}"
        multiplier = f"{acc.get('martingale_multiplier', 2.0):.1f}x"
        mart_enabled = 'Yes' if acc.get('martingale_enabled') else 'No'
        
        print(f"{name:<20} {ssid:<25} {is_demo:<6} {enabled:<8} {balance:<10} {base_amount:<8} {multiplier:<6} {mart_enabled:<6}")
    
    print(f"\nTotal accounts: {len(accounts)}")

def add_account_interactive(dm: DatabaseManager):
    """Add account with interactive prompts"""
    print("\n" + "="*50)
    print("ADD NEW ACCOUNT")
    print("="*50)
    
    worker_name = input("Account name/identifier: ").strip()
    if not worker_name:
        print("Error: Account name is required")
        return False
    
    ssid = input("SSID (email/login): ").strip()
    if not ssid:
        print("Error: SSID is required")
        return False
    
    is_demo_input = input("Is demo account? (y/N): ").strip().lower()
    is_demo = is_demo_input in ['y', 'yes', '1', 'true']
    
    enabled_input = input("Enable account? (Y/n): ").strip().lower()
    enabled = enabled_input not in ['n', 'no', '0', 'false']
    
    # Martingale settings
    print("\n--- Martingale Settings ---")
    
    try:
        base_amount_input = input("Base trade amount ($1.00): ").strip()
        base_amount = float(base_amount_input) if base_amount_input else 1.00
    except ValueError:
        base_amount = 1.00
        print("Invalid base amount, using $1.00")
    
    try:
        multiplier_input = input("Martingale multiplier (2.0): ").strip()
        martingale_multiplier = float(multiplier_input) if multiplier_input else 2.00
    except ValueError:
        martingale_multiplier = 2.00
        print("Invalid multiplier, using 2.0x")
    
    mart_enabled_input = input("Enable Martingale? (Y/n): ").strip().lower()
    martingale_enabled = mart_enabled_input not in ['n', 'no', '0', 'false']
    
    try:
        balance_input = input("Initial balance ($0.00): ").strip()
        balance = float(balance_input) if balance_input else 0.00
    except ValueError:
        balance = 0.00
        print("Invalid balance, using $0.00")
    
    # Confirm settings
    print("\n--- Confirm Account Settings ---")
    print(f"Name: {worker_name}")
    print(f"SSID: {ssid}")
    print(f"Demo: {'Yes' if is_demo else 'No'}")
    print(f"Enabled: {'Yes' if enabled else 'No'}")
    print(f"Balance: ${balance:.2f}")
    print(f"Base Amount: ${base_amount:.2f}")
    print(f"Multiplier: {martingale_multiplier:.1f}x")
    print(f"Martingale Enabled: {'Yes' if martingale_enabled else 'No'}")
    
    confirm = input("\nCreate account with these settings? (Y/n): ").strip().lower()
    if confirm in ['n', 'no', '0', 'false']:
        print("Account creation cancelled.")
        return False
    
    # Create account
    success = dm.add_account(
        worker_name=worker_name,
        ssid=ssid,
        is_demo=is_demo,
        enabled=enabled,
        balance=balance,
        base_amount=base_amount,
        martingale_multiplier=martingale_multiplier,
        martingale_enabled=martingale_enabled
    )
    
    if success:
        print(f"\n✅ Account '{worker_name}' created successfully!")
        return True
    else:
        print(f"\n❌ Failed to create account '{worker_name}'")
        return False

def update_martingale_settings_interactive(dm: DatabaseManager):
    """Update Martingale settings for an account"""
    print("\n" + "="*50)
    print("UPDATE MARTINGALE SETTINGS")
    print("="*50)
    
    # Show current accounts
    accounts = dm.get_all_accounts()
    if not accounts:
        print("No accounts found.")
        return False
    
    print("\nAvailable accounts:")
    for i, acc in enumerate(accounts, 1):
        print(f"{i}. {acc['worker_name']} (Base: ${acc.get('base_amount', 'N/A')}, "
              f"Mult: {acc.get('martingale_multiplier', 'N/A')}x, "
              f"Enabled: {'Yes' if acc.get('martingale_enabled') else 'No'})")
    
    try:
        choice = int(input(f"\nSelect account (1-{len(accounts)}): ")) - 1
        if choice < 0 or choice >= len(accounts):
            print("Invalid selection.")
            return False
        
        selected_account = accounts[choice]
        worker_name = selected_account['worker_name']
        
    except (ValueError, IndexError):
        print("Invalid selection.")
        return False
    
    print(f"\nUpdating Martingale settings for: {worker_name}")
    print("Leave blank to keep current value")
    
    # Get current settings
    current_settings = dm.get_account_martingale_settings(worker_name)
    if not current_settings:
        print("Failed to get current settings.")
        return False
    
    print(f"\nCurrent settings:")
    print(f"Base Amount: ${current_settings['base_amount']:.2f}")
    print(f"Multiplier: {current_settings['martingale_multiplier']:.1f}x")
    print(f"Enabled: {'Yes' if current_settings['martingale_enabled'] else 'No'}")
    
    # Get new values
    new_base = None
    new_multiplier = None
    new_enabled = None
    
    base_input = input(f"\nNew base amount (current: ${current_settings['base_amount']:.2f}): ").strip()
    if base_input:
        try:
            new_base = float(base_input)
        except ValueError:
            print("Invalid base amount.")
            return False
    
    mult_input = input(f"New multiplier (current: {current_settings['martingale_multiplier']:.1f}x): ").strip()
    if mult_input:
        try:
            new_multiplier = float(mult_input)
        except ValueError:
            print("Invalid multiplier.")
            return False
    
    enabled_input = input(f"Enable Martingale? y/n (current: {'y' if current_settings['martingale_enabled'] else 'n'}): ").strip().lower()
    if enabled_input:
        if enabled_input in ['y', 'yes', '1', 'true']:
            new_enabled = True
        elif enabled_input in ['n', 'no', '0', 'false']:
            new_enabled = False
        else:
            print("Invalid enabled value (use y/n).")
            return False
    
    # Apply updates
    if new_base is None and new_multiplier is None and new_enabled is None:
        print("No changes specified.")
        return False
    
    success = dm.update_account_martingale_settings(
        worker_name=worker_name,
        base_amount=new_base,
        martingale_multiplier=new_multiplier,
        martingale_enabled=new_enabled
    )
    
    if success:
        print(f"\n✅ Martingale settings updated for '{worker_name}'!")
        
        # Show updated settings
        updated_settings = dm.get_account_martingale_settings(worker_name)
        if updated_settings:
            print(f"\nUpdated settings:")
            print(f"Base Amount: ${updated_settings['base_amount']:.2f}")
            print(f"Multiplier: {updated_settings['martingale_multiplier']:.1f}x")
            print(f"Enabled: {'Yes' if updated_settings['martingale_enabled'] else 'No'}")
        
        return True
    else:
        print(f"\n❌ Failed to update Martingale settings for '{worker_name}'")
        return False

def toggle_account_status(dm: DatabaseManager):
    """Toggle account enabled/disabled status"""
    accounts = dm.get_all_accounts()
    if not accounts:
        print("No accounts found.")
        return False
    
    print("\n" + "="*50)
    print("TOGGLE ACCOUNT STATUS")
    print("="*50)
    
    print("\nAccounts:")
    for i, acc in enumerate(accounts, 1):
        status = "ENABLED" if acc['enabled'] else "DISABLED"
        print(f"{i}. {acc['worker_name']} - {status}")
    
    try:
        choice = int(input(f"\nSelect account to toggle (1-{len(accounts)}): ")) - 1
        if choice < 0 or choice >= len(accounts):
            print("Invalid selection.")
            return False
        
        selected_account = accounts[choice]
        worker_name = selected_account['worker_name']
        current_status = selected_account['enabled']
        new_status = not current_status
        
        success = dm.update_account_enabled_status(worker_name, new_status)
        
        if success:
            status_text = "ENABLED" if new_status else "DISABLED"
            print(f"\n✅ Account '{worker_name}' is now {status_text}")
            return True
        else:
            print(f"\n❌ Failed to toggle status for '{worker_name}'")
            return False
            
    except (ValueError, IndexError):
        print("Invalid selection.")
        return False

def main():
    """Main CLI interface"""
    parser = argparse.ArgumentParser(
        description="Enhanced Account Management for PocketOption Trading Bot",
        formatter_class=argparse.RawTextHelpFormatter
    )
    
    parser.add_argument('action', nargs='?', choices=[
        'list', 'enabled', 'add', 'martingale', 'toggle', 'help'
    ], default='help', help="""Available actions:
  list      - Show all accounts with settings
  enabled   - Show only enabled accounts
  add       - Add new account interactively
  martingale- Update Martingale settings
  toggle    - Toggle account enabled/disabled
  help      - Show this help message""")
    
    args = parser.parse_args()
    
    if args.action == 'help':
        parser.print_help()
        return
    
    # Initialize database
    try:
        dm = DatabaseManager()
        print("✅ Connected to database successfully")
    except Exception as e:
        print(f"❌ Failed to connect to database: {e}")
        return
    
    # Execute action
    try:
        if args.action == 'list':
            display_accounts(dm, enabled_only=False)
        
        elif args.action == 'enabled':
            display_accounts(dm, enabled_only=True)
        
        elif args.action == 'add':
            add_account_interactive(dm)
        
        elif args.action == 'martingale':
            update_martingale_settings_interactive(dm)
        
        elif args.action == 'toggle':
            toggle_account_status(dm)
        
    except KeyboardInterrupt:
        print("\n\n🛑 Operation cancelled by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
    finally:
        dm.close()

if __name__ == "__main__":
    main()
