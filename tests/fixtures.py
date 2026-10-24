"""
Standard test fixtures, seed data, and document payloads for RFP Response Assistant test suite.
Matches specifications in ORIGINAL_REQUEST.md, PROJECT.md, and verification_spec.md.
"""

# Default Services (5 items)
SEED_SERVICES = [
    {"id": 1, "name": "Web Development — Headless CMS"},
    {"id": 2, "name": "Digital Marketing — PPC"},
    {"id": 3, "name": "UX/UI Design"},
    {"id": 4, "name": "SEO — Technical"},
    {"id": 5, "name": "Mobile App Development"},
]

# Structured Price Items (6 items)
SEED_PRICE_ITEMS = [
    {
        "id": 1,
        "service_id": 1,
        "description": "Statamic Senior Developer",
        "unit": "day rate",
        "amount": 850.0,
    },
    {
        "id": 2,
        "service_id": 3,
        "description": "UX/UI Principal Designer",
        "unit": "day rate",
        "amount": 900.0,
    },
    {
        "id": 3,
        "service_id": 4,
        "description": "Technical SEO Audit",
        "unit": "fixed",
        "amount": 3500.0,
    },
    {
        "id": 4,
        "service_id": 2,
        "description": "Monthly PPC Management",
        "unit": "monthly retainer",
        "amount": 2200.0,
    },
    {
        "id": 5,
        "service_id": 1,
        "description": "Small Statamic Website Package",
        "unit": "fixed",
        "amount": 16500.0,
    },
    {
        "id": 6,
        "service_id": 1,
        "description": "Enterprise Statamic Retainer",
        "unit": "monthly retainer",
        "amount": 5000.0,
    },
]

# Knowledge Base Documents (5 items)
SEED_KB_DOCUMENTS = [
    {
        "id": 1,
        "type": "past_proposal",
        "title": "Enterprise Web Build for Retail Client",
        "content": (
            "Delivered an enterprise-grade Statamic headless CMS web platform for a major UK retail brand. "
            "Architecture utilized Statamic 4 with an Astro and Next.js frontend, microservices integration, "
            "and sub-second page loads. Total contract value £85k. Outcome: Won proposal."
        ),
        "outcome": "won",
        "service_ids": [1, 3],
    },
    {
        "id": 2,
        "type": "past_proposal",
        "title": "Digital Portal for Travel Agency",
        "content": (
            "Proposed a generic WordPress portal for European travel bookings with standard booking engine "
            "integration and shared database architecture. Total contract value £45k. Outcome: Lost proposal."
        ),
        "outcome": "lost",
        "service_ids": [1],
    },
    {
        "id": 3,
        "type": "case_study",
        "title": "Northwind Renewables Replatforming",
        "content": (
            "Another Marketing Agency replatformed Northwind Renewables from legacy infrastructure to a headless CMS. "
            "Results achieved: +140% mobile conversion rate, 99.99% system uptime during peak traffic, "
            "and carbon-neutral server hosting compliance."
        ),
        "outcome": "n/a",
        "service_ids": [1, 4],
    },
    {
        "id": 4,
        "type": "boilerplate",
        "title": "Another Marketing Agency Corporate Overview & Credentials",
        "content": (
            "Another Marketing Agency is a UK digital agency specialising in high-performance web development, digital marketing, and user experience design. "
            "We maintain ISO 27001 certified information security management, Cyber Essentials Plus accreditation, "
            "and £5,000,000 Professional Indemnity Insurance coverage. Our multidisciplinary team has delivered over "
            "120 public and private sector projects since 2016."
        ),
        "outcome": "n/a",
        "service_ids": [1, 2, 3, 4, 5],
    },
    {
        "id": 5,
        "type": "testimonial",
        "title": "Northwind Renewables CTO Commendation",
        "content": (
            "Another Marketing Agency delivered our digital transformation ahead of schedule and with flawless code quality. "
            "Their command of headless architecture solved our performance bottlenecks in record time."
        ),
        "outcome": "n/a",
        "service_ids": [1],
    },
]

# Master System Prompt & Tone of Voice Prompt
DEFAULT_SYSTEM_PROMPT = """You are an internal drafting assistant for Another Marketing Agency, a digital agency, helping staff prepare first-draft responses to Requests for Proposal (RFPs).

Your task is to generate a first draft for ONE section of an RFP response at a time.
You will be given:
- The original RFP question/requirement text for this section
- Retrieved reference material (past proposals, case studies, testimonials, pitch deck content) relevant to this section
- Structured pricing data, where relevant
- Boilerplate company information, where relevant
- Notes from the account manager (transcript excerpts, bullet points, or specific guidance for this project)

Rules:
1. Only use information present in the material provided. Never invent client names, figures, dates, credentials, past project details, or capabilities that are not explicitly present in your reference material.
2. Pricing figures must be reproduced exactly as given in the structured pricing data. Never estimate, round, or paraphrase a number.
3. If the provided material is insufficient to properly answer the section, write a brief, professional acknowledgement of the requirement (e.g. "We understand the need for..."), then insert the exact marker:
   [MORE INFO REQUIRED: brief description of what's missing]
   Do not attempt to plausibly guess the missing detail.
4. Match the structure, terminology, and level of detail implied by the original RFP question.
5. Write in the voice and style set out in the accompanying tone-of-voice instructions.
6. Output only the drafted section content, plus any [MORE INFO REQUIRED] markers. Do not include commentary about your own process."""

DEFAULT_TONE_PROMPT = """Write in Another Marketing Agency's house tone:
- Confident but not arrogant; direct and clear over clever or jargon-heavy
- Human and conversational, avoiding generic "corporate AI" phrasing (e.g. avoid "we are excited to leverage synergies")
- Short, punchy sentences over long compound ones where possible
- Show, don't just claim — back statements with specific evidence from case studies/testimonials rather than vague assertions of quality"""

# Default Settings
DEFAULT_SETTINGS = {
    "classification_model": "gemini-2.5-flash",
    "generation_model": "claude-sonnet-4-5",
    "claude_api_key": "sk-ant-test-mock-key",
    "gemini_api_key": "AIzaSy-test-mock-key",
    "mock_google_export": 1,
    "google_credentials_path": "credentials.json",
    "system_prompt": DEFAULT_SYSTEM_PROMPT,
    "tone_of_voice_prompt": DEFAULT_TONE_PROMPT,
}

# Sample RFP: "National Heritage Trust - Digital Visitor Experience & Portal" (7 sections)
SAMPLE_RFP_CLIENT = "National Heritage Trust"
SAMPLE_RFP_VALUE = 75000.0
SAMPLE_RFP_SERVICES = [1, 3]  # Web Development, UX/UI Design

SAMPLE_RFP_SECTIONS = [
    {
        "sort_order": 1,
        "heading": "1.0 Executive Summary & Agency Credentials",
        "original_text": (
            "Please provide an overview of your agency, key personnel, core accreditations, "
            "and information security standards relevant to public sector heritage organizations."
        ),
        "expected_classification": "boilerplate",
    },
    {
        "sort_order": 2,
        "heading": "2.0 Technical Approach — CMS Platform & Architecture",
        "original_text": (
            "Detail your proposed content management architecture. We require a modern, headless or decoupled CMS "
            "solution capable of serving fast, accessible content to over 500,000 monthly visitors."
        ),
        "expected_classification": "strategic_decision",
    },
    {
        "sort_order": 3,
        "heading": "3.0 Accessibility Compliance & Public Sector Standards",
        "original_text": (
            "Describe your recommended approach to accessibility compliance, including any relevant experience "
            "with public sector WCAG standards and user testing with assistive technology."
        ),
        # Deliberately ambiguous section (blends approach/decision with experience gap)
        "expected_classification": "strategic_decision",  # Or 'gap'
        "is_ambiguous": True,
    },
    {
        "sort_order": 4,
        "heading": "4.0 Project Timelines & Team Staffing",
        "original_text": (
            "Outline your proposed delivery phases, key milestones, and staffing allocation for a targeted 12-week deployment."
        ),
        "expected_classification": "boilerplate",
    },
    {
        "sort_order": 5,
        "heading": "5.0 Commercial Proposal & Rate Schedule",
        "original_text": (
            "Provide your complete pricing breakdown, including senior developer day rates, designer day rates, "
            "and fixed package costs for the initial website build."
        ),
        "expected_classification": "pricing",
    },
    {
        "sort_order": 6,
        "heading": "6.0 Experience with UK Public Health & NHS Telemetry Standards",
        "original_text": (
            "Detail your agency's verified past project experience implementing UK Public Health and NHS Digital "
            "telemetry compliance standards."
        ),
        "expected_classification": "gap",
    },
    {
        "sort_order": 7,
        "heading": "7.0 Mandatory Declarations & Sign-Off",
        "original_text": (
            "Confirm acceptance of standard terms, freedom of information provisions, and complete the tenderer declaration."
        ),
        "expected_classification": "compliance_admin",
    },
]
