import os
from dotenv import load_dotenv

load_dotenv()  # read .env into environment variables

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "openai/gpt-oss-120b")

LLM_TIMEOUT_S = 60          # max seconds for one LLM call
TOOL_TIMEOUT_S = 15         # max seconds per network operation in tools
MAX_PAGE_CHARS = 6000       # text kept from a fetched page (cost control)
MAX_DOWNLOAD_BYTES = 2_000_000  # never download more than ~2 MB per page
MAX_QUERIES_PER_TASK = 2    # search queries run per sub-task
MAX_SEARCHES = 7            # total searches per run (cost cap)
PAGES_PER_TASK = 2          # pages we try to read per sub-task
MAX_FETCH_ATTEMPTS = 12     # total page fetch attempts per run (cost/latency cap)
MAX_PER_DOMAIN = 2          # at most this many pages from one website (diversity)