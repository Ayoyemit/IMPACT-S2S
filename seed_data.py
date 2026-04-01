"""Seed the database with example strategies for development/testing."""
from models import db, Strategy


EXAMPLE_STRATEGIES = [
    # Provider level
    {"choice": "Train psychiatric nurses to provide brief behavioral counseling about smoking cessation",
     "level": "Provider", "primary_eric": "Conduct educational meetings",
     "help_text": "This involves training nursing staff in evidence-based brief interventions for smoking cessation during routine patient encounters."},
    {"choice": "Empower nurses to ask about smoking as they collect vitals for an appointment",
     "level": "Provider", "primary_eric": "Revise professional roles",
     "help_text": "Integrate smoking status assessment into the standard vital signs collection workflow."},
    {"choice": "Provide incentives to providers who complete smoking cessation training",
     "level": "Provider", "primary_eric": "Alter incentive/allowance structures",
     "help_text": "Offer financial or professional development incentives for completing certified training programs."},
    {"choice": "Develop a quick-reference guide for providers on smoking cessation medications",
     "level": "Provider", "primary_eric": "Develop educational materials",
     "help_text": "Create a concise pocket guide or digital reference tool listing approved pharmacotherapy options with dosing."},
    {"choice": "Include smoking cessation as a standing agenda item in clinical supervision",
     "level": "Provider", "primary_eric": "Provide clinical supervision", "help_text": ""},
    {"choice": "Offer peer mentoring between experienced and new providers on cessation counseling",
     "level": "Provider", "primary_eric": "Create a learning collaborative", "help_text": ""},

    # Organization level
    {"choice": "Integrate smoking status into the electronic health record intake form",
     "level": "Organization", "primary_eric": "Change record systems",
     "help_text": "Add mandatory smoking status fields to the EHR intake workflow so every patient is screened."},
    {"choice": "Create a dedicated smoking cessation coordinator role at each clinic",
     "level": "Organization", "primary_eric": "Revise professional roles",
     "help_text": "Designate a staff member responsible for coordinating all smoking cessation activities within the clinic."},
    {"choice": "Establish a smoke-free campus policy for the mental health center",
     "level": "Organization", "primary_eric": "Change physical structure and equipment", "help_text": ""},
    {"choice": "Provide on-site nicotine replacement therapy supplies for immediate dispensing",
     "level": "Organization", "primary_eric": "Change physical structure and equipment",
     "help_text": "Stock NRT products (patches, gum, lozenges) at the clinic for same-day access."},
    {"choice": "Schedule dedicated time blocks for smoking cessation group sessions",
     "level": "Organization", "primary_eric": "Assess and redesign workflow", "help_text": ""},
    {"choice": "Conduct regular audits of smoking cessation documentation completeness",
     "level": "Organization", "primary_eric": "Audit and provide feedback", "help_text": ""},

    # Organization + Provider (multi-level)
    {"choice": "Observe smoking cessation counseling sessions as part of clinical supervision",
     "level": "Organization, Provider", "primary_eric": "Audit and provide feedback",
     "help_text": "Supervisors directly observe provider counseling sessions and provide structured feedback for improvement."},
    {"choice": "Check in with providers about smoking cessation progress at staff meetings",
     "level": "Organization, Provider", "primary_eric": "Audit and provide feedback", "help_text": ""},

    # System level
    {"choice": "Advocate for Medicaid coverage of all FDA-approved smoking cessation medications",
     "level": "System", "primary_eric": "Access new funding",
     "help_text": "Work with policymakers to ensure comprehensive coverage of pharmacotherapy for Medicaid beneficiaries."},
    {"choice": "Develop partnerships between mental health centers and quitline services",
     "level": "System", "primary_eric": "Build a coalition",
     "help_text": "Create formal referral agreements between community mental health centers and state tobacco quitlines."},
    {"choice": "Create a statewide learning collaborative for smoking cessation in mental health",
     "level": "System", "primary_eric": "Create a learning collaborative", "help_text": ""},
    {"choice": "Lobby for tobacco tax increases with earmarked funding for mental health cessation programs",
     "level": "System", "primary_eric": "Access new funding", "help_text": ""},
    {"choice": "Develop a centralized training portal for smoking cessation in behavioral health",
     "level": "System", "primary_eric": "Centralize technical assistance", "help_text": ""},

    # Client level
    {"choice": "Provide free nicotine patches, gum, or lozenges for clients",
     "level": "Client", "primary_eric": "Alter patient/consumer fees",
     "help_text": "Eliminate cost barriers by providing NRT products at no charge to clients enrolled in the program."},
    {"choice": "Develop peer support groups led by clients who have successfully quit smoking",
     "level": "Client", "primary_eric": "Use mass media",
     "help_text": "Train former smokers with lived experience to facilitate peer-led support groups for current smokers."},
    {"choice": "Create culturally tailored smoking cessation materials for people with SMI",
     "level": "Client", "primary_eric": "Develop educational materials",
     "help_text": "Design brochures, videos, and digital content specifically adapted for the needs and literacy levels of people with serious mental illness."},
    {"choice": "Develop a protocol for helping clients navigate insurance for cessation medications",
     "level": "Client", "primary_eric": "Alter patient/consumer fees", "help_text": ""},
    {"choice": "Implement a client reward program for attending smoking cessation appointments",
     "level": "Client", "primary_eric": "Alter incentive/allowance structures", "help_text": ""},

    # Client + Provider (multi-level)
    {"choice": "Train clients to request smoking cessation support from their providers",
     "level": "Client, Provider", "primary_eric": "Prepare patients/consumers to be active participants",
     "help_text": "Educate and empower clients to initiate conversations about quitting with their treatment providers."},
]


def seed_example_data():
    """Insert example strategies if the database is empty."""
    if Strategy.query.count() == 0:
        for i, s in enumerate(EXAMPLE_STRATEGIES, start=1):
            strategy = Strategy(
                original_id=float(i),
                choice=s["choice"],
                level=s["level"],
                primary_eric=s["primary_eric"],
                help_text=s.get("help_text", ""),
                is_active=True,
                is_user_submitted=False,
            )
            db.session.add(strategy)
        db.session.commit()
        print(f"Seeded {len(EXAMPLE_STRATEGIES)} example strategies.")
    else:
        print(f"Database already has {Strategy.query.count()} strategies. Skipping seed.")
