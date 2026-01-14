import asyncio

from simclass.app.config import resolve_paths
from simclass.app.llm_factory import LLMFactory
from simclass.app.scenario import load_scenario
from simclass.core.simulation import Simulation
from simclass.core.tools import build_default_tools
from simclass.infra import SQLiteMemoryStore, configure_logging, load_dotenv


def run() -> None:
    configure_logging()
    paths = resolve_paths()
    load_dotenv(paths.root / ".env")
    scenario = load_scenario(paths.config_path)
    store = SQLiteMemoryStore(paths.data_path)
    llm_factory = LLMFactory(scenario.llm)
    tool_registry = build_default_tools()
    simulation = Simulation(scenario, store, llm_factory, tool_registry)
    asyncio.run(simulation.run())
