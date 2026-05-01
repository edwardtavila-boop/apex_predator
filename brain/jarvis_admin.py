# Wave-17 Autonomous mode — Jarvis may self-approve routine operations
# when the system is healthy (stress < 0.3, TRADE tier) and the action
# is in the AUTONOMOUS_ACTIONS allowlist. All other actions still gate through
# normal policy. Autonomous decisions are fully audited with reason_code
# "autonomous_trade" and cannot override KILL, STAND_ASIDE, or REDUCE tiers.
AUTONOMOUS_ACTIONS: frozenset[ActionType] = frozenset(
    {
        ActionType.ORDER_PLACE,
        ActionType.ORDER_MODIFY,
        ActionType.ORDER_CANCEL,
        ActionType.POSITION_FLATTEN,
        ActionType.SIGNAL_EMIT,
        ActionType.PARAMETER_CHANGE,
        ActionType.REBALANCE,
        ActionType.STRATEGY_DEPLOY,
        ActionType.STRATEGY_RETIRE,
    }
)

# Subsystems permitted to operate autonomously (proven bots only).
# New/unproven bots must still go through operator approval until promoted.
AUTONOMOUS_SUBSYSTEMS: frozenset[SubsystemId] = frozenset(
    {
        SubsystemId.BOT_MNQ,
        SubsystemId.BOT_BTC_PERP,
        SubsystemId.BOT_ETH_PERP,
        SubsystemId.BOT_SOL_PERP,
        SubsystemId.BOT_XRP_PERP,
    }
)