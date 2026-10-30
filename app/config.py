import os
from dotenv import load_dotenv

load_dotenv()  # read .env into environment variables

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "openai/gpt-oss-120b")

LLM_TIMEOUT_S = 60          # max seconds for one LLM call
LLM_MAX_TOKENS = 4096   # explicit output cap; reasoning models can run out of tokens mid-JSON
TOOL_TIMEOUT_S = 15         # max seconds per network operation in tools
MAX_PAGE_CHARS = 6000       # text kept from a fetched page (cost control)
MAX_DOWNLOAD_BYTES = 2_000_000  # never download more than ~2 MB per page
MAX_QUERIES_PER_TASK = 2    # search queries run per sub-task
MAX_SEARCHES = 7            # total searches per run (cost cap)
PAGES_PER_TASK = 2          # pages we try to read per sub-task
MAX_FETCH_ATTEMPTS = 12     # total page fetch attempts per run (cost/latency cap)
MAX_PER_DOMAIN = 2          # at most this many pages from one website (diversity)
MIN_RELEVANCE = 0.4              # sources scoring below this are dropped
MAX_SOURCES_FOR_SYNTHESIS = 6    # cost cap on what the synthesizer reads
TRIAGE_EXCERPT_CHARS = 500       # how much of each page the triage step sees
SYNTH_CHARS_PER_SOURCE = 3500    # how much of each page the synthesizer sees
