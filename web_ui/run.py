#!/usr/bin/env python3
"""
HuboluxTradingBot Web UI - Application Runner
"""

import os
import sys
from app import create_app

def main():
    """Main application entry point"""
    
    # Get port from environment or default to 9001
    port = int(os.environ.get('PORT', 9001))
    
    # ASCII Art Banner
    print("\n" + "="*66)
    print("║" + " "*21 + "HuboluxTradingBot Web UI" + " "*21 + "║")
    print("║" + " "*40 + "║")
    print("=" + "="*64 + "=")
    print(f"║ 🌐 Server:    http://127.0.0.1:{port}" + " "*(31-len(str(port))) + "║")
    print("║ 🔧 Mode:      Development" + " "*36 + "║")
    print("║ 🗄️  Database:  Using existing bot database" + " "*19 + "║")
    print("║ 👤 Default:   admin / admin123" + " "*32 + "║")
    print("║ ⚡ Frontend:  Alpine.js for reactivity" + " "*23 + "║")
    print("=" + "="*64 + "=")
    print()
    
    # Get configuration
    config_name = os.environ.get('FLASK_ENV', 'development')
    
    # Create the Flask app
    app = create_app(config_name)
    
    # Run the application
    app.run(
        host='127.0.0.1',
        port=port,
        debug=True,
        use_reloader=True
    )

if __name__ == '__main__':
    main()
