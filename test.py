import os
from parallel import Parallel
from dotenv import load_dotenv
load_dotenv()

client = Parallel(api_key=os.getenv("PARALLEL_API_KEY"))

search = client.beta.search(
    objective="Latest news in India",
    search_queries=[
        "India news",
        "India today news"
    ],
    max_results=10,
    max_chars_per_result=10000
)

print(type(search.results))
print(search)
