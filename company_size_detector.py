"""
Company size and type detector — classify companies by size and industry.
========================================================================

Categorizes companies by:
- Size: startup, small, mid, large, enterprise
- Business type: IT/Software, AI/ML, Finance, Healthcare, etc.
- Coworking detection: flags shared office spaces
"""


def detect_company_size(company_data: dict) -> str:
    """Detect company size from name, website, description, AND address.

    Returns: 'startup', 'small', 'mid', 'large', or 'enterprise'
    """
    name = (company_data.get("company_name") or "").lower()
    website = (company_data.get("website") or "").lower()
    description = (company_data.get("description") or "").lower()
    address = (company_data.get("address") or "").lower()
    building_name = (company_data.get("building_name") or "").lower()

    # Enterprise signals
    if any(x in name for x in ["google", "microsoft", "amazon", "facebook", "apple", "ibm", "hp", "dell"]):
        return "enterprise"
    if any(x in website for x in [".com.au", ".co.uk", ".gov", ".edu"]) and "startup" not in name:
        return "large"
    if any(x in name for x in ["corp", "limited", "ltd", "inc", "plc", "sa"]):
        if "startup" not in name and "incubator" not in name:
            return "large"

    # Address-based size detection
    # Large company address patterns
    if any(x in address for x in ["tower", "plaza", "business park", "corporate park", "business centre", "business center"]):
        if "startup" not in name and "co-working" not in address:
            return "large"
    if any(x in building_name for x in ["tower", "plaza", "park", "centre", "center", "complex", "hub"]):
        if "startup" not in name:
            return "large"

    # Startup signals
    if any(x in name for x in ["startup", "incubator", "accelerator", "labs", "studio", "garage"]):
        return "startup"
    if any(x in website for x in [".io", ".dev", ".ai", ".co"]):
        return "startup"
    if any(x in address for x in ["incubator", "accelerator", "startup hub", "startup space"]):
        return "startup"

    # Mid-sized signals
    if any(x in name for x in ["enterprise", "group", "global", "international"]):
        return "mid"
    if any(x in building_name for x in ["enterprise", "global"]):
        return "mid"

    # Small company signals
    if any(x in name for x in ["services", "solutions", "consulting", "agency"]):
        return "small"
    if any(x in address for x in ["floor", "unit", "office", "suite"]):
        if "tower" not in address and "plaza" not in address:
            return "small"

    # Default to small/mid if industry is tech
    if "software" in description or "technology" in description or "it " in description:
        return "small"

    return "small"


def detect_business_type(company_data: dict) -> str:
    """Detect primary business type from name, industry, description, address.

    Returns: 'IT / Software', 'AI / ML', 'Finance', 'Healthcare', etc.
    """
    name = (company_data.get("company_name") or "").lower()
    industry = (company_data.get("industry") or "").lower()
    description = (company_data.get("description") or "").lower()
    website = (company_data.get("website") or "").lower()
    address = (company_data.get("address") or "").lower()

    text = f"{name} {industry} {description} {address}".lower()

    # AI/ML
    if any(x in text for x in ["ai ", "ml", "machine learning", "artificial intelligence", "llm", "neural", "nlp", "deep learning"]):
        return "AI / ML"

    # IT/Software
    if any(x in text for x in ["software", "it ", "development", "technology", "web", "app", "saas", "platform"]):
        return "IT / Software"

    # Finance
    if any(x in text for x in ["bank", "finance", "fintech", "insurance", "trading", "investment", "fintech", "crypto"]):
        return "Finance"

    # Healthcare
    if any(x in text for x in ["health", "medical", "pharma", "hospital", "clinic", "doctor"]):
        return "Healthcare"

    # Education
    if any(x in text for x in ["education", "training", "school", "course", "edtech", "university"]):
        return "Education"

    # E-commerce
    if any(x in text for x in ["ecommerce", "retail", "shop", "store", "marketplace"]):
        return "E-commerce"

    # Consulting
    if any(x in text for x in ["consulting", "consulting", "advisory", "consulting firm"]):
        return "Consulting"

    return industry or "Other"


def is_coworking_space(company_data: dict) -> bool:
    """Check if this is a coworking space or shared office building using all available data."""
    name = (company_data.get("company_name") or "").lower()
    industry = (company_data.get("industry") or "").lower()
    description = (company_data.get("description") or "").lower()
    address = (company_data.get("address") or "").lower()
    building_name = (company_data.get("building_name") or "").lower()

    coworking_keywords = [
        "coworking", "co-working", "cowork", "shared office", "office space",
        "workspace", "work space", "business center", "flex office",
        "wework", "awfis", "smartworks", "91springboard", "innov8", "regus",
        "indiqube", "tablespace", "cowrks", "incuspaze", "worknest",
        "springhouse", "spring house", "devx", "collab", "myhq",
        "co working", "shared workspace", "collaborative office", "flex space",
        "hot desk", "hotdesk"
    ]

    text = f"{name} {industry} {description} {address} {building_name}".lower()
    return any(keyword in text for keyword in coworking_keywords)


def enrich_with_size_info(companies: list) -> list:
    """Add size and type classification to each company."""
    if not companies:
        return companies

    for company in companies:
        company["company_size"] = detect_company_size(company)
        company["business_type"] = detect_business_type(company)
        company["is_coworking_space"] = is_coworking_space(company)

    return companies
