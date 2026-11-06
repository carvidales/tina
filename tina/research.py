"""Opt-in, bounded TradingAgents crypto research. No exchange or operator credentials."""
import copy
import logging
import multiprocessing as mp
import os
import time
from datetime import datetime, timezone
import httpx
from tina.models import Research

log = logging.getLogger(__name__)
SYMBOLS = {"BTC/EUR": "BTC-USD", "ETH/EUR": "ETH-USD"}
RATINGS = {"Buy", "Overweight", "Hold", "Underweight", "Sell", "REVIEW"}


def run_graph(symbol, provider, quick, deep):
    from tradingagents.default_config import DEFAULT_CONFIG
    from tradingagents.graph.trading_graph import TradingAgentsGraph
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    cfg.update(llm_provider=provider, quick_think_llm=quick, deep_think_llm=deep,
               max_debate_rounds=1, max_risk_discuss_rounds=1, max_tool_rounds=3,
               max_recur_limit=100, max_tokens=1200, llm_max_retries=1, checkpoint_enabled=False)
    graph = TradingAgentsGraph(selected_analysts=["market", "social", "news"], config=cfg)
    state, signal = graph.propagate(symbol, datetime.now(timezone.utc).date().isoformat(), asset_type="crypto")
    rating = signal if isinstance(signal, str) and signal in RATINGS else "REVIEW"
    fields = ("market_report", "sentiment_report", "news_report", "final_trade_decision")
    return rating, "\n\n".join(str(state.get(k, "")) for k in fields)[:15000]


def _child(pipe, symbol, provider, quick, deep):
    try:
        pipe.send(run_graph(symbol, provider, quick, deep))
    except Exception as exc:
        pipe.send(("REVIEW", "Research failed: " + type(exc).__name__))
    finally:
        pipe.close()


def analyze(pair, provider, quick, deep, timeout=600):
    started = time.time()
    ctx = mp.get_context("spawn")
    receive, send = ctx.Pipe(duplex=False)
    process = ctx.Process(target=_child, args=(send, SYMBOLS[pair], provider, quick, deep))
    process.start()
    send.close()
    try:
        rating, summary = receive.recv() if receive.poll(timeout) else ("REVIEW", "Research deadline exceeded")
    except EOFError:
        rating, summary = "REVIEW", "Research worker exited without a report"
    finally:
        process.join(timeout=1)
        if process.is_alive():
            process.terminate()
            process.join(timeout=5)
        if process.is_alive():
            process.kill()
            process.join()
        receive.close()
    return Research(pair=pair, source_symbol=SYMBOLS[pair], started_at=started,
                    completed_at=time.time(), rating=rating, summary=summary,
                    provider=provider, model=f"{quick} / {deep}")


def main():
    logging.basicConfig(level=logging.INFO)
    provider = os.environ.get("TINA_LLM_PROVIDER", "")
    quick, deep = os.environ.get("TINA_QUICK_MODEL", ""), os.environ.get("TINA_DEEP_MODEL", "")
    token = os.environ.get("TINA_RESEARCH_TOKEN", "")
    if not provider or not quick or not deep or len(token) < 32:
        raise SystemExit("Set provider/model IDs, its API key, and the research token before enabling research")
    interval = max(3600, int(os.environ.get("TINA_RESEARCH_INTERVAL", "3600")))
    url = os.environ.get("TINA_CONTROL_URL", "http://control:8081")
    with httpx.Client(timeout=10, trust_env=False, headers={"Authorization": "Bearer " + token}) as client:
        while True:
            cycle_start = time.monotonic()
            for pair in SYMBOLS:
                try:
                    report = analyze(pair, provider, quick, deep)
                    client.post(url + "/v1/research", json=report.model_dump()).raise_for_status()
                except Exception as exc:
                    log.warning("Report unavailable for %s (%s)", pair, type(exc).__name__)
            time.sleep(max(60, interval - (time.monotonic() - cycle_start)))


if __name__ == "__main__":
    main()
