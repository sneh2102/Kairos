# install first if needed:
# pip install langgraph ipython

from IPython.display import Image, display
from screener import screen_job  # We'll need to adapt this
import inspect

def main():
    # Since screener doesn't have a graph.build function like apply_graph,
    # we'll create a visualization of the screener function flow instead

    # Get the source code of the screen_job function
    source_lines = inspect.getsource(screen_job)

    # For now, let's create a simple Mermaid diagram representing the screener flow
    mermaid_source = '''---
config:
  flowchart:
    curve: linear
---
graph TD
    A[Start: screen_job(client, job, cfg, resume_text)] --> B[Get prompt template]
    B --> C[Build candidate profile]
    C --> D[Add custom rules from cfg[screener]]
    D --> E[Format prompt with job data]
    E --> F[Call LLM client]
    F --> G[Parse verdict JSON]
    G --> H{Check blacklist?}
    H -->|Yes match| I[Force verdict = "no"<br/>Reason: "Blacklisted company"]
    H -->|No match| J[Return parsed verdict]
    I --> J
    J --> K[End: Return verdict dict]'''

    # Save Mermaid source
    with open("screener_flow.mmd", "w", encoding="utf-8") as f:
        f.write(mermaid_source)

    print("Mermaid source saved as screener_flow.mmd")

    # Try to generate PNG if we have the right dependencies
    try:
        # This would require a graph object like in apply_graph
        # Since we don't have that, we'll just note that the user can use the mermaid file
        print("To generate PNG, use:")
        print("  mmdc -i screener_flow.mmd -o screener_flow.png")
        print("  (requires mermaid-cli: npm install -g @mermaid-js/mermaid-cli)")
    except Exception as e:
        print(f"Could not generate PNG: {e}")

if __name__ == "__main__":
    main()