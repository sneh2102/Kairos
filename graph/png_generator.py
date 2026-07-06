# install first if needed:
# pip install langgraph ipython

from IPython.display import Image, display
from apply_graph import build_apply_graph

def main():
    # Build and compile the graph
    app = build_apply_graph()

    # Generate PNG
    png_data = app.get_graph().draw_mermaid_png()

    # Save PNG
    output_file = "apply_graph.png"
    with open(output_file, "wb") as f:
        f.write(png_data)

    print(f"Graph saved as {output_file}")

    # Display (works in Jupyter Notebook)
    display(Image(png_data))

    # Optional: Save Mermaid source
    with open("apply_graph.mmd", "w", encoding="utf-8") as f:
        f.write(app.get_graph().draw_mermaid())

    print("Mermaid source saved as apply_graph.mmd")


if __name__ == "__main__":
    main()