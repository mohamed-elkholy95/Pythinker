import json

report_content = '''
# Comprehensive Research Report on Manus: Skills and Features

**Author:** Manus AI
**Date:** January 31, 2026

## 1. Introduction

This report provides a comprehensive analysis of the skills and features of Manus, an autonomous general AI agent. It details the implementation of these features, their integration within Manus\'s workflow, and their practical applications. The research was conducted using parallel processing to ensure a thorough and precise examination of each component, offering deep insights into the technical aspects and operational methodologies that define Manus.

## 2. Core Capabilities

Manus is equipped with a suite of core capabilities that enable it to perform a wide range of tasks. These capabilities are exposed through a set of tools that the agent can invoke to interact with its environment, process information, and generate outputs. The following sections provide a detailed analysis of each core capability.
'''

with open("/home/ubuntu/manus_research_report.md", "w") as f:
    f.write(report_content)

with open("/home/ubuntu/manus_feature_research.json", "r") as f:
    research_results = json.load(f)

for result in research_results["results"]:
    feature_name = result["input"].split(":")[0].strip().capitalize()
    feature_description = result["input"].split(":")[1].strip()
    technical_details = result["output"]["technical_details"]
    workflow_integration = result["output"]["workflow_integration"]
    practical_applications = result["output"]["practical_applications"]
    constraints_and_best_practices = result["output"]["constraints_and_best_practices"]

    report_content += f"\n### {feature_name}: {feature_description}\n\n"
    report_content += f"**Technical Details:**\n{technical_details}\n\n"
    report_content += f"**Workflow Integration:**\n{workflow_integration}\n\n"
    report_content += f"**Practical Applications:**\n{practical_applications}\n\n"
    report_content += f"**Constraints and Best Practices:**\n{constraints_and_best_practices}\n\n"

report_content += "\n## 3. Conclusion\n\nThis report has provided a detailed examination of Manus\'s skills and features, highlighting their technical underpinnings, integration into the agent\'s workflow, and practical utility. The modular design, coupled with advanced capabilities like parallel processing and multimodal understanding, positions Manus as a highly versatile and efficient autonomous agent capable of addressing complex tasks across various domains.\n"

with open("/home/ubuntu/manus_research_report.md", "w") as f:
    f.write(report_content)
