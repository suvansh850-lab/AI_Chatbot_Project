"""CrewAI orchestration for data analysis and report compilation agents."""

import os
import json

try:
    from crewai import Agent, Task, Crew, Process
    from crewai.tools import tool
    CREWAI_AVAILABLE = True
except ImportError:
    CREWAI_AVAILABLE = False
    # Define dummy tools & decorator for compatibility
    def tool(*args, **kwargs):
        def decorator(func):
            return func
        return decorator

from .report_service import generate_pdf_report, generate_excel_report, generate_pptx_report

# ─── 1. Custom CrewAI Tools for Document Output ───

@tool("PDF Document Builder")
def create_pdf_tool(title: str, headers_json: str, rows_json: str, summary: str) -> str:
    """Useful to generate a PDF report containing tables.
    headers_json must be a JSON array of strings (headers).
    rows_json must be a JSON array of arrays (rows).
    """
    try:
        headers = json.loads(headers_json)
        rows = json.loads(rows_json)
        url = generate_pdf_report(title, headers, rows, summary)
        return f"PDF report successfully created. Download URL: {url}"
    except Exception as e:
        return f"Error creating PDF: {str(e)}"

@tool("Excel Spreadsheet Builder")
def create_excel_tool(title: str, headers_json: str, rows_json: str) -> str:
    """Useful to generate an Excel spreadsheet.
    headers_json must be a JSON array of strings (headers).
    rows_json must be a JSON array of arrays (rows).
    """
    try:
        headers = json.loads(headers_json)
        rows = json.loads(rows_json)
        url = generate_excel_report(title, headers, rows)
        return f"Excel spreadsheet successfully created. Download URL: {url}"
    except Exception as e:
        return f"Error creating Excel: {str(e)}"

@tool("PowerPoint Slides Builder")
def create_pptx_tool(title: str, bullets_json: str) -> str:
    """Useful to generate a PowerPoint slide presentation.
    bullets_json must be a JSON array of strings.
    """
    try:
        bullets = json.loads(bullets_json)
        url = generate_pptx_report(title, bullets)
        return f"PowerPoint presentation successfully created. Download URL: {url}"
    except Exception as e:
        return f"Error creating PPTX: {str(e)}"


# ─── 2. CrewAI Agent & Task Execution ───

def run_report_crew(sales_raw_data: str, report_format: str = "pdf") -> str:
    """Kick off the Crew to analyze data and compile the report file."""
    if not CREWAI_AVAILABLE:
        return (
            "CrewAI package is not installed. To run this agent team, "
            "please run 'pip install crewai' on your host system."
        )
        
    # Define Agents
    analyst_agent = Agent(
        role="Senior Sales Data Analyst",
        goal="Analyze raw transaction data, calculate totals, identify growth trends, and summarize findings.",
        backstory="An expert financial data scientist with a background in corporate sales auditing and trend diagnostics.",
        verbose=True,
        memory=True
    )
    
    designer_agent = Agent(
        role="Report Layout Designer",
        goal="Format data summaries and tables into polished layouts and export them using document builders.",
        backstory="A technical reporting expert specializing in compiling data insights into clean PDF, Excel, or PPTX sheets.",
        tools=[create_pdf_tool, create_excel_tool, create_pptx_tool],
        verbose=True
    )
    
    # Define Tasks
    analysis_task = Task(
        description=f"Analyze this raw sales log:\n{sales_raw_data}\nIsolate key metrics: total revenue, best performing items, and average ticket size.",
        expected_output="A structured text summary detailing key performance indicators (KPIs) and data grids ready for reporting.",
        agent=analyst_agent
    )
    
    compilation_task = Task(
        description=(
            f"Take the analysis output and export it as a {report_format.upper()} report. "
            f"Use the corresponding Tool (PDF, Excel, or PowerPoint Builder). "
            f"Format all table columns and rows as JSON strings to feed into the tool inputs. "
            f"For PDF/Excel, build a structured data grid. For PPTX, compile core summary bullets."
        ),
        expected_output=f"A confirm message containing the download URL returned by the {report_format.upper()} document tool.",
        agent=designer_agent
    )
    
    # Assemble Crew
    report_crew = Crew(
        agents=[analyst_agent, designer_agent],
        tasks=[analysis_task, compilation_task],
        process=Process.sequential
    )
    
    result = report_crew.kickoff()
    return str(result)
