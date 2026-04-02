"""Built-in memory templates for common patterns."""
from __future__ import annotations

from memoria.templates.schema import FieldSpec, MemoryTemplate

BUILTIN_TEMPLATES: list[MemoryTemplate] = [
    MemoryTemplate(
        name="coding_preference",
        description="Store a coding/framework/tool preference",
        category="developer",
        fields=[
            FieldSpec(name="language", type="string", required=True, description="Programming language"),
            FieldSpec(name="framework", type="string", description="Framework or library"),
            FieldSpec(name="style_guide", type="string", description="Style guide or conventions"),
            FieldSpec(name="formatting", type="string", description="Formatting preferences"),
        ],
        content_template=(
            "User preference: {language} development\n"
            "Framework: {framework}\n"
            "Style: {style_guide}\n"
            "Formatting: {formatting}"
        ),
        tags=["preference", "coding", "developer"],
        default_tier="core",
        default_importance=0.8,
        builtin=True,
    ),
    MemoryTemplate(
        name="project_context",
        description="Project description, tech stack, and conventions",
        category="developer",
        fields=[
            FieldSpec(name="project_name", type="string", required=True, description="Project name"),
            FieldSpec(name="description", type="string", required=True, description="What the project does"),
            FieldSpec(name="tech_stack", type="string", description="Technologies used"),
            FieldSpec(name="conventions", type="string", description="Coding conventions"),
            FieldSpec(name="repo_url", type="string", description="Repository URL"),
        ],
        content_template=(
            "Project: {project_name}\n"
            "Description: {description}\n"
            "Tech Stack: {tech_stack}\n"
            "Conventions: {conventions}\n"
            "Repo: {repo_url}"
        ),
        tags=["project", "context", "developer"],
        default_tier="core",
        default_importance=0.9,
        builtin=True,
    ),
    MemoryTemplate(
        name="bug_report",
        description="Bug description, reproduction steps, and resolution",
        category="engineering",
        fields=[
            FieldSpec(name="title", type="string", required=True, description="Bug title"),
            FieldSpec(name="description", type="string", required=True, description="Bug description"),
            FieldSpec(name="steps_to_reproduce", type="string", description="Steps to reproduce"),
            FieldSpec(name="expected_behavior", type="string", description="Expected behavior"),
            FieldSpec(name="actual_behavior", type="string", description="Actual behavior"),
            FieldSpec(name="resolution", type="string", description="How it was fixed"),
        ],
        content_template=(
            "Bug: {title}\n"
            "{description}\n\n"
            "Steps to reproduce:\n{steps_to_reproduce}\n\n"
            "Expected: {expected_behavior}\n"
            "Actual: {actual_behavior}\n\n"
            "Resolution: {resolution}"
        ),
        tags=["bug", "issue", "engineering"],
        default_tier="working",
        default_importance=0.7,
        builtin=True,
    ),
    MemoryTemplate(
        name="meeting_notes",
        description="Meeting summary, decisions, and action items",
        category="collaboration",
        fields=[
            FieldSpec(name="title", type="string", required=True, description="Meeting title"),
            FieldSpec(name="date", type="string", description="Meeting date"),
            FieldSpec(name="attendees", type="string", description="Who attended"),
            FieldSpec(name="summary", type="string", required=True, description="Key discussion points"),
            FieldSpec(name="decisions", type="string", description="Decisions made"),
            FieldSpec(name="action_items", type="string", description="Follow-up tasks"),
        ],
        content_template=(
            "Meeting: {title} ({date})\n"
            "Attendees: {attendees}\n\n"
            "Summary:\n{summary}\n\n"
            "Decisions:\n{decisions}\n\n"
            "Action Items:\n{action_items}"
        ),
        tags=["meeting", "notes", "collaboration"],
        default_tier="working",
        default_importance=0.6,
        builtin=True,
    ),
    MemoryTemplate(
        name="api_endpoint",
        description="API route, parameters, auth, and response schema",
        category="developer",
        fields=[
            FieldSpec(name="method", type="string", required=True, description="HTTP method (GET, POST, etc.)"),
            FieldSpec(name="path", type="string", required=True, description="Endpoint path"),
            FieldSpec(name="description", type="string", description="What the endpoint does"),
            FieldSpec(name="auth", type="string", description="Authentication requirements"),
            FieldSpec(name="params", type="string", description="Parameters"),
            FieldSpec(name="response", type="string", description="Response schema/example"),
        ],
        content_template=(
            "API: {method} {path}\n"
            "{description}\n\n"
            "Auth: {auth}\n"
            "Parameters: {params}\n"
            "Response: {response}"
        ),
        tags=["api", "endpoint", "developer"],
        default_tier="core",
        default_importance=0.8,
        builtin=True,
    ),
    MemoryTemplate(
        name="design_decision",
        description="Architecture Decision Record — context, decision, consequences",
        category="engineering",
        fields=[
            FieldSpec(name="title", type="string", required=True, description="Decision title"),
            FieldSpec(name="context", type="string", required=True, description="Why this decision was needed"),
            FieldSpec(name="decision", type="string", required=True, description="What was decided"),
            FieldSpec(name="alternatives", type="string", description="Alternatives considered"),
            FieldSpec(name="consequences", type="string", description="Impact and trade-offs"),
        ],
        content_template=(
            "ADR: {title}\n\n"
            "Context:\n{context}\n\n"
            "Decision:\n{decision}\n\n"
            "Alternatives:\n{alternatives}\n\n"
            "Consequences:\n{consequences}"
        ),
        tags=["adr", "decision", "architecture"],
        default_tier="core",
        default_importance=0.9,
        builtin=True,
    ),
    MemoryTemplate(
        name="customer_profile",
        description="SaaS customer info, subscription, and usage patterns",
        category="business",
        fields=[
            FieldSpec(name="name", type="string", required=True, description="Customer/company name"),
            FieldSpec(name="plan", type="string", description="Subscription plan"),
            FieldSpec(name="usage", type="string", description="Usage patterns"),
            FieldSpec(name="preferences", type="string", description="Customer preferences"),
            FieldSpec(name="notes", type="string", description="Additional notes"),
        ],
        content_template=(
            "Customer: {name}\n"
            "Plan: {plan}\n"
            "Usage: {usage}\n"
            "Preferences: {preferences}\n"
            "Notes: {notes}"
        ),
        tags=["customer", "profile", "business"],
        default_tier="working",
        default_importance=0.7,
        builtin=True,
    ),
    MemoryTemplate(
        name="incident_report",
        description="Incident timeline, root cause, and remediation",
        category="engineering",
        fields=[
            FieldSpec(name="title", type="string", required=True, description="Incident title"),
            FieldSpec(name="severity", type="string", required=True, description="Severity level"),
            FieldSpec(name="timeline", type="string", description="Timeline of events"),
            FieldSpec(name="root_cause", type="string", description="Root cause analysis"),
            FieldSpec(name="remediation", type="string", description="What was done to fix it"),
            FieldSpec(name="prevention", type="string", description="Steps to prevent recurrence"),
        ],
        content_template=(
            "Incident: {title} (Severity: {severity})\n\n"
            "Timeline:\n{timeline}\n\n"
            "Root Cause:\n{root_cause}\n\n"
            "Remediation:\n{remediation}\n\n"
            "Prevention:\n{prevention}"
        ),
        tags=["incident", "postmortem", "engineering"],
        default_tier="core",
        default_importance=0.9,
        builtin=True,
    ),
    MemoryTemplate(
        name="onboarding_step",
        description="Onboarding task, status, and dependencies",
        category="collaboration",
        fields=[
            FieldSpec(name="task", type="string", required=True, description="Onboarding task"),
            FieldSpec(name="status", type="string", description="Task status"),
            FieldSpec(name="assignee", type="string", description="Person responsible"),
            FieldSpec(name="dependencies", type="string", description="Dependencies"),
            FieldSpec(name="notes", type="string", description="Additional notes"),
        ],
        content_template=(
            "Onboarding: {task}\n"
            "Status: {status}\n"
            "Assignee: {assignee}\n"
            "Dependencies: {dependencies}\n"
            "Notes: {notes}"
        ),
        tags=["onboarding", "task", "collaboration"],
        default_tier="working",
        default_importance=0.5,
        builtin=True,
    ),
    MemoryTemplate(
        name="knowledge_article",
        description="Documentation with category, tags, and links",
        category="documentation",
        fields=[
            FieldSpec(name="title", type="string", required=True, description="Article title"),
            FieldSpec(name="content", type="string", required=True, description="Article content"),
            FieldSpec(name="category", type="string", description="Content category"),
            FieldSpec(name="related_links", type="string", description="Related resources"),
        ],
        content_template=(
            "# {title}\n\n"
            "{content}\n\n"
            "Category: {category}\n"
            "Related: {related_links}"
        ),
        tags=["knowledge", "documentation", "article"],
        default_tier="core",
        default_importance=0.7,
        builtin=True,
    ),
]
