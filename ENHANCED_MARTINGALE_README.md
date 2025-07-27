# Enhanced Martingale Trading System

## Overview

The Enhanced Martingale Trading System is an advanced implementation of the Martingale strategy that supports intelligent concurrent trading with configurable settings and persistent MySQL storage. This system provides fine-grained control over trade management while maintaining compatibility with the existing bot architecture.

## Key Features

### ✅ Concurrency Control
- **Configurable concurrent trading**: Enable or disable concurrent trades per account
- **Smart trade queuing**: If concurrency is disabled, new trades wait for previous trades to complete
- **Account-level isolation**: Each account has independent concurrency settings

### ✅ Martingale Threading (Smart Lanes)
- **Independent lanes**: Each failed trade creates a separate "Martingale lane" or track
- **Lane-specific tracking**: Each lane maintains its own level, stake amount, and win/loss status
- **Persistent state**: All lane data is stored in MySQL and survives bot restarts
- **Unique identification**: Each lane has a unique ID for precise tracking

### ✅ Intelligent Trade Assignment
- **Strategy-based assignment**: FIFO, Round-Robin, or Symbol Priority assignment strategies
- **Automatic lane creation**: New lanes are created automatically on trade failures
- **Priority handling**: Existing lanes get priority over new base trades
- **Flexible routing**: Single trade can be assigned to appropriate lane automatically

### ✅ Advanced Win/Loss Handling
- **Lane completion**: Winning Martingale trades complete their respective lanes
- **Independent tracking**: Base trade wins don't affect existing Martingale lanes
- **Progressive scaling**: Losing trades advance their lanes with calculated amounts
- **Max level protection**: Lanes automatically complete when reaching maximum level

### ✅ MySQL Integration
- **Persistent storage**: All lane data stored in `martingale_lanes` table
- **Trading settings**: Account-specific settings in `trading_settings` table
- **Restart resilience**: System state survives bot restarts and crashes
- **Performance tracking**: Comprehensive statistics and reporting

## Database Schema

### Martingale Lanes Table
```sql
CREATE TABLE martingale_lanes (
    id INTEGER PRIMARY KEY AUTO_INCREMENT,
    lane_id VARCHAR(100) UNIQUE NOT NULL,
    account_name VARCHAR(100) NOT NULL,
    symbol VARCHAR(50) NOT NULL,
    status ENUM('active', 'completed', 'cancelled') DEFAULT 'active',
    current_level INTEGER DEFAULT 1,
    base_amount DECIMAL(10,2) NOT NULL,
    current_amount DECIMAL(10,2) NOT NULL,
    multiplier DECIMAL(5,2) NOT NULL,
    max_level INTEGER DEFAULT 7,
    total_invested DECIMAL(10,2) DEFAULT 0.00,
    total_potential_payout DECIMAL(10,2) DEFAULT 0.00,
    trade_ids TEXT DEFAULT '[]',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    completed_at TIMESTAMP NULL
);
```

### Trading Settings Table
```sql
CREATE TABLE trading_settings (
    id INTEGER PRIMARY KEY AUTO_INCREMENT,
    account_name VARCHAR(100) UNIQUE NOT NULL,
    concurrent_trading_enabled BOOLEAN DEFAULT FALSE,
    max_concurrent_lanes INTEGER DEFAULT 3,
    lane_assignment_strategy ENUM('fifo', 'round_robin', 'symbol_priority') DEFAULT 'fifo',
    auto_create_lanes BOOLEAN DEFAULT TRUE,
    cool_down_seconds INTEGER DEFAULT 0,
    max_daily_lanes INTEGER DEFAULT 10,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
```

## Configuration and Management

### Using the Management Script

The `manage_enhanced_martingale.py` script provides comprehensive management capabilities:

#### List All Accounts and Settings
```bash
python manage_enhanced_martingale.py list
```

#### Enable Concurrent Trading
```bash
python manage_enhanced_martingale.py configure pelly_demo --concurrent true --max-lanes 5
```

#### Configure Assignment Strategy
```bash
python manage_enhanced_martingale.py configure pelly_demo --strategy round_robin --auto-create true
```

#### View Statistics
```bash
python manage_enhanced_martingale.py stats --account pelly_demo --days 7
```

#### Force Complete Stuck Lanes
```bash
python manage_enhanced_martingale.py complete lane_id_here --status cancelled
```

### Configuration Options

| Setting | Description | Default | Values |
|---------|-------------|---------|---------|
| `concurrent_trading_enabled` | Allow multiple trades simultaneously | `false` | `true/false` |
| `max_concurrent_lanes` | Maximum active lanes per account | `3` | `1-10` |
| `lane_assignment_strategy` | How to assign trades to lanes | `fifo` | `fifo`, `round_robin`, `symbol_priority` |
| `auto_create_lanes` | Auto-create lanes on trade losses | `true` | `true/false` |
| `cool_down_seconds` | Delay between trades | `0` | `0-3600` |
| `max_daily_lanes` | Maximum new lanes per day | `10` | `1-50` |

## Lane Assignment Strategies

### FIFO (First In, First Out)
- Assigns trades to the oldest active lane first
- Simple and predictable behavior
- Good for sequential recovery

### Round Robin
- Distributes trades evenly across all active lanes
- Balances lane progression
- Optimal for multiple concurrent recoveries

### Symbol Priority
- Prioritizes lanes with matching symbols
- Falls back to FIFO for non-matching symbols
- Good for symbol-specific strategies

## Usage Examples

### Basic Setup
```python
# Enable concurrent trading with 3 lanes
python manage_enhanced_martingale.py configure pelly_demo \
  --concurrent true \
  --max-lanes 3 \
  --strategy fifo
```

### Conservative Setup
```python
# Disable concurrency, auto-create only
python manage_enhanced_martingale.py configure pelly_demo \
  --concurrent false \
  --auto-create true \
  --max-daily-lanes 5
```

### Aggressive Setup
```python
# High concurrency with round-robin
python manage_enhanced_martingale.py configure pelly_demo \
  --concurrent true \
  --max-lanes 7 \
  --strategy round_robin \
  --max-daily-lanes 20
```

## Integration with Existing System

The Enhanced Martingale system is designed to be backward-compatible:

1. **Automatic fallback**: If Enhanced system fails, falls back to legacy Martingale
2. **Gradual migration**: Can be enabled per-account without affecting others
3. **Existing settings**: Respects existing base amounts and multipliers from accounts table
4. **Legacy support**: Original Martingale functions continue to work

## Monitoring and Debugging

### Status Logging
The bot automatically logs Enhanced Martingale status every 60 seconds, showing:
- Active lanes per account
- Concurrency settings
- Lane details (symbol, level, amount)
- Overall system health

### Available Functions
```python
# Get comprehensive status
status = detectsignal.get_current_martingale_status()

# Configure settings programmatically
detectsignal.configure_enhanced_martingale_settings('pelly_demo', 
    concurrent_trading_enabled=True, max_concurrent_lanes=5)

# Get statistics
stats = detectsignal.get_enhanced_martingale_statistics('pelly_demo', days=7)

# Force complete lanes
detectsignal.force_complete_martingale_lane('lane_id_here')
```

## Best Practices

### 1. Start Conservative
- Begin with concurrent trading disabled
- Use `max_lanes=2` for testing
- Monitor performance before increasing limits

### 2. Set Appropriate Limits
- `max_daily_lanes` prevents runaway lane creation
- `cool_down_seconds` can help avoid rapid-fire trades
- `max_level=7` prevents excessive escalation

### 3. Choose Right Strategy
- **FIFO**: Good for single-threaded recovery approach
- **Round Robin**: Best for balanced multiple recoveries
- **Symbol Priority**: Use if you trade specific symbols frequently

### 4. Monitor Regularly
- Check lane statistics daily
- Watch for stuck or excessive lanes
- Monitor win/loss ratios per lane

### 5. Emergency Procedures
- Use `force_complete_lane` for stuck lanes
- Emergency stop: disable `auto_create_lanes`
- Reset: complete all active lanes and restart

## Troubleshooting

### Common Issues

1. **Lanes not being created**
   - Check `auto_create_lanes` is enabled
   - Verify `max_daily_lanes` not exceeded
   - Ensure account Martingale is enabled

2. **Too many concurrent lanes**
   - Reduce `max_concurrent_lanes`
   - Check lane completion logic
   - Force complete old lanes if needed

3. **Trades not being assigned to lanes**
   - Verify Enhanced system is initialized
   - Check for database connection issues
   - Review assignment strategy settings

4. **Performance issues**
   - Monitor database query performance
   - Consider reducing `max_concurrent_lanes`
   - Check for memory usage with many lanes

### Debugging Commands
```bash
# Check system status
python -c "
from enhanced_martingale import get_enhanced_martingale_manager
mgr = get_enhanced_martingale_manager()
if mgr: print(mgr.get_current_status())
"

# View active lanes
python manage_enhanced_martingale.py list

# Check recent statistics
python manage_enhanced_martingale.py stats --days 1
```

## Migration from Legacy System

The Enhanced Martingale system can run alongside the legacy system:

1. **Phase 1**: Deploy Enhanced system with `concurrent_trading_enabled=false`
2. **Phase 2**: Enable concurrency on test accounts
3. **Phase 3**: Gradually enable on production accounts
4. **Phase 4**: Optional - disable legacy fallback once confident

## Performance Considerations

- **Database queries**: Enhanced system makes additional DB queries for lane management
- **Memory usage**: Lane caching reduces DB load but uses more memory
- **Concurrent processing**: More complex logic may slightly slow trade processing
- **Recovery**: Faster recovery from losses due to intelligent lane management

## Security and Risk Management

- **Max level limits**: Prevents infinite escalation
- **Daily limits**: `max_daily_lanes` prevents excessive exposure
- **Account isolation**: Each account's lanes are independent
- **Emergency stops**: Multiple ways to halt runaway trading
- **Audit trail**: Complete database logging of all lane activities
