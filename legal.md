AI classification and documentation
Since Digistore24 operates in the EU, the AI Act applies. An AI-System firstly needs to accessed on its risk categery formally:
A developer tool operating on internal code is probably not high-risk, but if the agent ever touches systems that process payment data, personal data at scale, or safety-relevant logic, that assessment shifts.
Even for limited-risk or minimal-risk systems, we have transparency obligations. Anyone interacting with AI-generated output needs to know it's AI-generated trough labelling (e.g. in Slack)
We'll need to document this use-case in our internal AI inventory.
What I need from you: A clear documentation showing the reasoning behind decisions and possibilities of intervention, what the agent can access, what it can modify, and what approval gates exist before code hits any branch that feeds into production.
Human Oversight & Approval Gates
This is both a legal requirement and a practical one:
No AI-generated code should be merged without explicit human approval.
No AI-triggered Jira changes should go live without a human in the loop for anything beyond status updates.
A clear chain of responsibility and accountability for bugs or vulnerabilities introduced by the AI-System and who is to fix them.
What I need from you: Confirmation of where human checkpoints exist in each of the three interfaces (GitHub Actions, Jira Automation, Slack App) in additional documentation of the use-case and how responsibilities are handled along the process-chain.
