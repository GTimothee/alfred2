from dotenv import load_dotenv

from git_bash_controller import list_git_bash_windows, get_git_status
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.prebuilt import create_react_agent
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()

system_prompt = """You are a super AI assistant with access to tools to help the user achieve their goals."""

model = ChatGoogleGenerativeAI(model="gemini-2.0-flash", temperature=0)

checkpointer = InMemorySaver()


agent = create_react_agent(
    model=model,
    prompt=system_prompt,
    tools=[list_git_bash_windows, get_git_status],
    checkpointer=checkpointer
)

response = agent.invoke(
    {"messages": [{"role": "user", "content": "how many bash shells are open and what is the folder in which they are ?"}]},
    config={"configurable": {"thread_id": "1"}},
    context={"user_id": "1"}
)

print("Answer: ", response['messages'][-1].content)  

response = agent.invoke(
    {"messages": response['messages'] + [{"role": "user", "content": "can you see if there is any file ready to be committed in the Alfred project?"}]},
    config={"configurable": {"thread_id": "1"}},
    context={"user_id": "1"}
)

print("Answer: ", response['messages'][-1].content)  