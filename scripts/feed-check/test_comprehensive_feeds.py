#!/usr/bin/env python3
"""
Comprehensive test script for all cybersecurity RSS feeds from HTML table.
Tests both media and vendor feeds.
"""

import asyncio
import aiohttp
import xml.etree.ElementTree as ET
from html import unescape
import json

# Parse feeds from the HTML table - comprehensive list
COMPREHENSIVE_FEEDS = {
    # Media feeds
    'cybersecuritynews_all': {'name': 'Cyber Security News', 'url': 'https://cybersecuritynews.com/feed/'},
    'cybersecuritynews_ai': {'name': 'Cyber Security News (AI)', 'url': 'https://cybersecuritynews.com/category/cyber-ai/feed/'},
    'cybersecuritynews_attack': {'name': 'Cyber Security News (Attack)', 'url': 'https://cybersecuritynews.com/category/cyber-attack/feed/'},
    'cybersecuritynews_breach': {'name': 'Cyber Security News (Breaches)', 'url': 'https://cybersecuritynews.com/category/data-breaches/feed/'},
    'cybersecuritynews_threats': {'name': 'Cyber Security News (Threats)', 'url': 'https://cybersecuritynews.com/category/threats/feed/'},
    'cybersecuritynews_vuln': {'name': 'Cyber Security News (Vulnerability)', 'url': 'https://cybersecuritynews.com/category/vulnerability/feed/'},
    'cybersecuritynews_zeroday': {'name': 'Cyber Security News (Zero-Day)', 'url': 'https://cybersecuritynews.com/category/zero-day/feed/'},
    'cyberscoop_cybercrime': {'name': 'Cyberscoop (Cyber Crime)', 'url': 'https://cyberscoop.com/news/threats/cybercrime/feed'},
    'cyberscoop_research': {'name': 'Cyberscoop (Research)', 'url': 'https://cyberscoop.com/news/research/feed/'},
    'cyberscoop_threats': {'name': 'Cyberscoop (Threats)', 'url': 'https://cyberscoop.com/news/threats/feed/'},
    'gbhackers': {'name': 'GBHackers', 'url': 'https://gbhackers.com/feed/'},
    'gbhackers_breach': {'name': 'GBHackers (Data Breach)', 'url': 'https://gbhackers.com/category/data-breach/feed/'},
    'gbhackers_threats': {'name': 'GBHackers (Threats)', 'url': 'https://gbhackers.com/category/threatsattacks/feed/'},
    'gbhackers_vuln': {'name': 'GBHackers (Vulnerabilities)', 'url': 'https://gbhackers.com/category/vulnerability-android-2/feed/'},
    'govinfosecurity': {'name': 'GovInfoSecurity', 'url': 'https://www.govinfosecurity.com/rss-feeds'},
    'grahamcluley_dataloss': {'name': 'Graham Cluley (Data Loss)', 'url': 'https://grahamcluley.com/category/data-loss/feed/'},
    'grahamcluley_law': {'name': 'Graham Cluley (Law & Order)', 'url': 'https://grahamcluley.com/category/law-order/feed'},
    'grahamcluley_malware': {'name': 'Graham Cluley (Malware)', 'url': 'https://grahamcluley.com/category/security-threats/malware/feed/'},
    'grahamcluley_mobile': {'name': 'Graham Cluley (Mobile)', 'url': 'https://grahamcluley.com/category/mobile/feed/'},
    'grahamcluley_privacy': {'name': 'Graham Cluley (Privacy)', 'url': 'https://grahamcluley.com/category/privacy/feed/'},
    'grahamcluley_ransomware': {'name': 'Graham Cluley (Ransomware)', 'url': 'https://grahamcluley.com/category/security-threats/ransomware-malware/feed/'},
    'grahamcluley_spam': {'name': 'Graham Cluley (Spam)', 'url': 'https://grahamcluley.com/category/spam/feed/'},
    'hackercombat': {'name': 'Hacker Combat', 'url': 'https://www.hackercombat.com/feed/'},
    'hackercombat_hacks': {'name': 'Hacker Combat (Hacks)', 'url': 'https://www.hackercombat.com/category/hacks/feed/'},
    'hackercombat_malware': {'name': 'Hacker Combat (Malware)', 'url': 'https://www.hackercombat.com/category/malware-attacks/feed/'},
    'hackercombat_ransomware': {'name': 'Hacker Combat (Ransomware)', 'url': 'https://www.hackercombat.com/category/ransomware/feed/'},
    'hackread_anon': {'name': 'HackRead (Anonymous)', 'url': 'https://www.hackread.com/hacking-news/anonymous/feed/'},
    'hackread_ai': {'name': 'HackRead (AI)', 'url': 'https://www.hackread.com/artificial-intelligence/feed/'},
    'hackread_blockchain': {'name': 'HackRead (Blockchain)', 'url': 'https://www.hackread.com/blockchain/feed/'},
    'hackread_crypto': {'name': 'HackRead (Cryptocurrency)', 'url': 'https://www.hackread.com/cryptocurrency/feed/'},
    'hackread_cyberattack': {'name': 'HackRead (Cyber Attacks)', 'url': 'https://www.hackread.com/cyber-events/cyber-attacks-cyber-events/feed/'},
    'hackread_cybercrime': {'name': 'HackRead (Cyber Crime)', 'url': 'https://www.hackread.com/latest-cyber-crime/feed/'},
    'hackread_hacking': {'name': 'HackRead (Hacking News)', 'url': 'https://www.hackread.com/hacking-news/feed/'},
    'hackread_leaks': {'name': 'HackRead (Leaks)', 'url': 'https://www.hackread.com/hacking-news/leaks-affairs/feed/'},
    'hackread_ml': {'name': 'HackRead (Machine Learning)', 'url': 'https://www.hackread.com/artificial-intelligence/machine-learning/feed/'},
    'hackread_malware': {'name': 'HackRead (Malware)', 'url': 'https://www.hackread.com/security/malware/feed/'},
    'hackread_phishing': {'name': 'HackRead (Phishing)', 'url': 'https://www.hackread.com/latest-cyber-crime/phishing-scam/feed/'},
    'hackread_privacy': {'name': 'HackRead (Privacy)', 'url': 'https://www.hackread.com/surveillance/privacy/feed/'},
    'hackread_scams': {'name': 'HackRead (Scams)', 'url': 'https://www.hackread.com/latest-cyber-crime/scams-and-fraud/feed/'},
    'hackread_security': {'name': 'HackRead (Security)', 'url': 'https://www.hackread.com/security/feed/'},
    'hackread_surveillance': {'name': 'HackRead (Surveillance)', 'url': 'https://www.hackread.com/surveillance/feed/'},
    'infosec_appsec': {'name': 'Infosecurity Magazine (App Security)', 'url': 'https://www.infosecurity-magazine.com/rss/application-security/'},
    'infosec_automation': {'name': 'Infosecurity Magazine (Automation)', 'url': 'https://www.infosecurity-magazine.com/rss/automation/'},
    'infosec_cloud': {'name': 'Infosecurity Magazine (Cloud)', 'url': 'https://www.infosecurity-magazine.com/rss/cloud-security/'},
    'infosec_cybercrime': {'name': 'Infosecurity Magazine (Cybercrime)', 'url': 'https://www.infosecurity-magazine.com/rss/cybercrime/'},
    'infosec_malware': {'name': 'Infosecurity Magazine (Malware)', 'url': 'https://www.infosecurity-magazine.com/rss/malware/'},
    'infosec_privacy': {'name': 'Infosecurity Magazine (Privacy)', 'url': 'https://www.infosecurity-magazine.com/rss/privacy/'},
    'nextgov_cyber': {'name': 'NextGov (Cybersecurity)', 'url': 'https://www.nextgov.com/rss/cybersecurity/'},
    'securityaffairs_apt': {'name': 'Security Affairs (APT)', 'url': 'https://securityaffairs.com/category/apt/feed'},
    'securityaffairs_cybercrime': {'name': 'Security Affairs (Cyber Crime)', 'url': 'https://securityaffairs.com/category/cyber-crime/feed'},
    'securityaffairs_cyberwar': {'name': 'Security Affairs (Cyber warfare)', 'url': 'https://securityaffairs.com/category/cyber-warfare-2/feed'},
    'securityaffairs_breach': {'name': 'Security Affairs (Data Breach)', 'url': 'https://securityaffairs.com/category/data-breach/feed'},
    'securityaffairs_hacking': {'name': 'Security Affairs (Hacking)', 'url': 'https://securityaffairs.com/category/hacking/feed'},
    'securityaffairs_malware': {'name': 'Security Affairs (Malware)', 'url': 'https://securityaffairs.com/category/malware/feed'},
    'securityaffairs_security': {'name': 'Security Affairs (Security)', 'url': 'https://securityaffairs.com/category/security/feed'},
    'securityboulevard': {'name': 'Security Boulevard', 'url': 'https://securityboulevard.com/feed/'},
    'securityonline': {'name': 'Security Online', 'url': 'https://securityonline.info/feed/'},
    'securityonline_cyber': {'name': 'Security Online (Cyber Security)', 'url': 'https://securityonline.info/category/news/cybersecurity/feed/'},
    'securityonline_dataleak': {'name': 'Security Online (Data Leak)', 'url': 'https://securityonline.info/category/news/dataleak/feed/'},
    'securityonline_malware': {'name': 'Security Online (Malware)', 'url': 'https://securityonline.info/category/news/malware/feed/'},
    'securityonline_vuln': {'name': 'Security Online (Vulnerability)', 'url': 'https://securityonline.info/category/news/vulnerability/feed/'},
    'securityweek_appsec': {'name': 'SecurityWeek (App Security)', 'url': 'https://www.securityweek.com/category/application-security/feed/'},
    'securityweek_cloud': {'name': 'SecurityWeek (Cloud Security)', 'url': 'https://www.securityweek.com/category/cloud-security/feed/'},
    'securityweek_cybercrime': {'name': 'SecurityWeek (Cybercrime)', 'url': 'https://www.securityweek.com/category/cybercrime/feed/'},
    'securityweek_breach': {'name': 'SecurityWeek (Data Breaches)', 'url': 'https://www.securityweek.com/category/data-breaches/feed/'},
    'securityweek_ics': {'name': 'SecurityWeek (ICS/OT)', 'url': 'https://www.securityweek.com/category/ics-ot/feed/'},
    'securityweek_malware': {'name': 'SecurityWeek (Malware)', 'url': 'https://www.securityweek.com/category/malware-cyber-threats/feed/'},
    'securityweek_ransomware': {'name': 'SecurityWeek (Ransomware)', 'url': 'https://www.securityweek.com/category/ransomware/feed/'},
    'securityweek_threatintel': {'name': 'SecurityWeek (Threat Intelligence)', 'url': 'https://www.securityweek.com/category/threat-intelligence/feed/'},
    'securityweek_vuln': {'name': 'SecurityWeek (Vulnerabilities)', 'url': 'https://www.securityweek.com/category/vulnerabilities/feed/'},
    'techcrunch_security': {'name': 'TechCrunch (Security)', 'url': 'https://techcrunch.com/category/security/feed/'},
    'cyberexpress_darkweb': {'name': 'The Cyber Express (Dark Web)', 'url': 'https://thecyberexpress.com/firewall-daily/dark-web-news/feed/'},
    'cyberexpress_breach': {'name': 'The Cyber Express (Breaches)', 'url': 'https://thecyberexpress.com/firewall-daily/data-breaches-news/feed/'},
    'cyberexpress_hacker': {'name': 'The Cyber Express (Hacker News)', 'url': 'https://thecyberexpress.com/firewall-daily/hacker-news/feed/'},
    'cyberexpress_ransomware': {'name': 'The Cyber Express (Ransomware)', 'url': 'https://thecyberexpress.com/firewall-daily/ransomware-news/feed/'},
    'cyberexpress_vuln': {'name': 'The Cyber Express (Vulnerabilities)', 'url': 'https://thecyberexpress.com/firewall-daily/vulnerabilities/feed/'},
    'thecyberwire': {'name': 'The Cyber Wire', 'url': 'https://thecyberwire.com/feeds/rss.xml'},
    'thehackernews': {'name': 'The Hacker News', 'url': 'https://feeds.feedburner.com/TheHackersNews'},
    'theregister': {'name': 'The Register (Security)', 'url': 'https://www.theregister.com/security/headlines.atom'},
    'securityledger': {'name': 'The Security Ledger', 'url': 'https://feeds.feedblitz.com/thesecurityledger&x=1'},
    'threatpost_malware': {'name': 'Threatpost (Malware)', 'url': 'https://threatpost.com/category/malware-2/feed/'},
    'threatpost_vuln': {'name': 'Threatpost (Vulnerabilities)', 'url': 'https://threatpost.com/category/vulnerabilities/feed/'},
    
    # Additional vendor feeds not in previous lists
    '360cert': {'name': '360 CERT', 'url': 'https://cert.360.cn/feed'},
    'ahnlab': {'name': 'AhnLab Security Intelligence', 'url': 'https://asec.ahnlab.com/en/feed/'},
    'ahnlab_detection': {'name': 'AhnLab (Detection)', 'url': 'https://asec.ahnlab.com/en/category/detection-en/feed/'},
    'ahnlab_malware': {'name': 'AhnLab (Malware)', 'url': 'https://asec.ahnlab.com/en/category/malware-information-en/feed/'},
    'analyst1': {'name': 'Analyst1', 'url': 'https://analyst1.com/category/blog/feed/'},
    'anyrun_malware': {'name': 'ANY.RUN (Malware Analysis)', 'url': 'https://any.run/cybersecurity-blog/category/malware-analysis/feed/'},
    'binarydefense_threatintel': {'name': 'Binary Defense (Threat Intelligence)', 'url': 'https://www.binarydefense.com/resources/tag/threat-intelligence/feed/'},
    'binarydefense_research': {'name': 'Binary Defense (Threat Research)', 'url': 'https://www.binarydefense.com/resources/tag/threat-research/feed/'},
    'binarydefense': {'name': 'Binary Defense', 'url': 'https://www.binarydefense.com/feed/'},
    'blackhills_blue': {'name': 'Black Hills (Blue Team)', 'url': 'https://www.blackhillsinfosec.com/category/blue-team/feed/'},
    'brandefense': {'name': 'BRANDEFENSE', 'url': 'https://brandefense.io/blog/rss/'},
    'cadosecurity': {'name': 'Cado Security', 'url': 'https://www.cadosecurity.com/feed/'},
    'cis_advisory': {'name': 'CIS (Advisories)', 'url': 'https://www.cisecurity.org/feed/advisories'},
    'checkmarx': {'name': 'Checkmarx', 'url': 'https://medium.com/feed/checkmarx-security'},
    'cisco_umbrella': {'name': 'Cisco Umbrella', 'url': 'https://umbrella.cisco.com/feed'},
    'cofense_labnotes': {'name': 'Cofense (Lab Notes)', 'url': 'https://cofense.com/blog/category/lab-notes/feed/'},
    'cofense_phishing': {'name': 'Cofense (Phishing)', 'url': 'https://cofense.com/blog/category/phishing-email-insights/feed/'},
    'cofense_threatintel': {'name': 'Cofense (Threat Intel)', 'url': 'https://cofense.com/blog/category/threat-intelligence-insights/feed/'},
    'crowdstrike_threat_feed': {'name': 'Crowdstrike (Threat Research Feed)', 'url': 'https://www.crowdstrike.com/blog/category/threat-intel-research/feed'},
    'cybereason': {'name': 'Cybereason', 'url': 'https://www.cybereason.com/blog/rss.xml'},
    'cyble': {'name': 'Cyble', 'url': 'https://cyble.com/blog/feed/'},
    'datadog_security': {'name': 'Datadog Security Labs', 'url': 'https://securitylabs.datadoghq.com/rss/feed.xml'},
    'drweb_mobile': {'name': 'Doctor Web (Mobile)', 'url': 'https://news.drweb.com/rss/get/?c=38'},
    'drweb_realtime': {'name': 'Doctor Web (Real-time)', 'url': 'https://news.drweb.com/rss/get/?c=23'},
    'drweb_virus': {'name': 'Doctor Web (Virus)', 'url': 'https://news.drweb.com/rss/get/?c=10'},
    'domaintools': {'name': 'DomainTools', 'url': 'https://www.domaintools.com/resources/blog/feed/'},
    'ecrime': {'name': 'eCrime.ch', 'url': 'https://ecrime.ch/app/intel-news.php?rss'},
    'falconforce': {'name': 'FalconForce', 'url': 'https://medium.com/feed/falconforce'},
    'fidelis': {'name': 'Fidelis Security', 'url': 'https://fidelissecurity.com/feed/'},
    'fortinet_threat_feed': {'name': 'Fortinet (Threat Research Feed)', 'url': 'https://feeds.fortinet.com/fortinet/blog/threat-research&x=1'},
    'github_security': {'name': 'GitHub Security Lab', 'url': 'https://github.blog/tag/github-security-lab/feed/'},
    'google_tag': {'name': 'Google Threat Analysis Group', 'url': 'https://blog.google/threat-analysis-group/rss/'},
    'greynoise': {'name': 'GreyNoise Labs', 'url': 'https://www.labs.greynoise.io/grimoire/index.xml'},
    'groupib': {'name': 'Group IB', 'url': 'https://blog.group-ib.com/rss.xml'},
    'haveibeenpwned': {'name': 'Have I Been Pwned', 'url': 'https://feeds.feedburner.com/HaveIBeenPwnedLatestBreaches'},
    'heimdal_threat': {'name': 'Heimdal (Threat Center)', 'url': 'https://heimdalsecurity.com/blog/category/threat-center/feed/'},
    'heimdal_vuln': {'name': 'Heimdal (Vulnerability)', 'url': 'https://heimdalsecurity.com/blog/category/vulnerability/feed/'},
    'huntress': {'name': 'Huntress', 'url': 'https://www.huntress.com/blog/rss.xml'},
    'infoblox_cti': {'name': 'Infoblox (CTI)', 'url': 'https://blogs.infoblox.com/category/cyber-threat-intelligence/feed/'},
    'infostealers': {'name': 'Infostealers by HudsonRock', 'url': 'https://www.infostealers.com/feed/'},
    'infostealers_malware': {'name': 'Infostealers (Malware)', 'url': 'https://www.infostealers.com/topic/malware/feed/'},
    'infostealers_topic': {'name': 'Infostealers (Topic)', 'url': 'https://www.infostealers.com/topic/infostealers/feed/'},
    'intezer_research': {'name': 'Intezer (Research)', 'url': 'https://intezer.com/blog/research/feed/'},
    'knowbe4_ransomware': {'name': 'KnowBe4 (Ransomware)', 'url': 'https://blog.knowbe4.com/topic/ransomware/rss.xml'},
    'knowbe4': {'name': 'KnowBe4', 'url': 'https://blog.knowbe4.com/rss.xml'},
    'lab52': {'name': 'Lab52', 'url': 'https://lab52.io/blog/feed/'},
    'mandiant': {'name': 'Mandiant', 'url': 'https://www.mandiant.com/resources/blog/rss.xml'},
    'mcafee_labs': {'name': 'McAfee Labs (Labs)', 'url': 'https://www.mcafee.com/blogs/other-blogs/mcafee-labs/feed/'},
    'morphisec': {'name': 'Morphisec', 'url': 'https://blog.morphisec.com/rss.xml'},
    'nextron': {'name': 'Nextron', 'url': 'https://www.nextron-systems.com/feed/'},
    'outpost24': {'name': 'Outpost24 (Research)', 'url': 'https://outpost24.com/blog/category/research-and-threat-intel/feed/'},
    'paloalto_unit42_feed': {'name': 'PaloAlto Unit 42 (Feed)', 'url': 'http://feeds.feedburner.com/Unit42'},
    'pulsedive': {'name': 'Pulsedive', 'url': 'https://blog.pulsedive.com/rss/'},
    'qualys_threat': {'name': 'Qualys (Threat Research)', 'url': 'https://blog.qualys.com/vulnerabilities-threat-research/feed'},
    'quickheal_threat': {'name': 'Quick Heal (Threat Research)', 'url': 'https://blogs.quickheal.com/author/threat-research-labs/feed/'},
    'recorded_future': {'name': 'Recorded Future', 'url': 'https://www.recordedfuture.com/feed'},
    'redcanary': {'name': 'Red Canary', 'url': 'https://redcanary.com/feed/'},
    'reliaquest_hunting': {'name': 'Reliaquest (Threat Hunting)', 'url': 'https://www.reliaquest.com/blog/category/threat-hunting/feed/'},
    'reliaquest_intel': {'name': 'Reliaquest (Threat Intelligence)', 'url': 'https://www.reliaquest.com/blog/category/threat-intelligence/feed/'},
    'reversinglabs': {'name': 'ReversingLabs', 'url': 'https://www.reversinglabs.com/blog/tag/threat-research/rss.xml'},
    'rstcloud': {'name': 'RST Cloud', 'url': 'https://medium.com/@rst_cloud/feed'},
    'securelist_kaspersky': {'name': 'SecureList (Kaspersky)', 'url': 'https://securelist.com/feed/'},
    'securitylit': {'name': 'Security Lit', 'url': 'https://securitylit.medium.com/feed'},
    'sekoia': {'name': 'Sekoia', 'url': 'https://blog.sekoia.io/feed/'},
    'sekoia_research': {'name': 'Sekoia (Research)', 'url': 'https://blog.sekoia.io/category/research-threat-intelligence/feed/'},
    'sentinelone_blog': {'name': 'SentinelOne Blog', 'url': 'https://www.sentinelone.com/blog/feed/'},
    'seqrite': {'name': 'Seqrite', 'url': 'https://www.seqrite.com/blog/feed/'},
    'slashnext': {'name': 'SlashNext', 'url': 'https://slashnext.com/feed/'},
    'sophos_threat': {'name': 'Sophos (Threat Research)', 'url': 'https://news.sophos.com/en-us/category/threat-research/feed/'},
    'teamcymru': {'name': 'Team Cymru', 'url': 'https://www.team-cymru.com/blog-feed.xml'},
    'tenable_blog': {'name': 'Tenable Blog', 'url': 'https://www.tenable.com/blog/feed'},
    'therecord_cybercrime': {'name': 'The Record (Cybercrime)', 'url': 'https://therecord.media/news/cybercrime/feed/'},
    'therecord_nationstate': {'name': 'The Record (Nation State)', 'url': 'https://therecord.media/news/nation-state/feed/'},
    'therecord_tech': {'name': 'The Record (Technology)', 'url': 'https://therecord.media/news/technology/feed/'},
    'threatmon': {'name': 'Threatmon', 'url': 'https://threatmon.io/blog/feed/'},
    'trustedsec': {'name': 'TrustedSec', 'url': 'https://trustedsec.com/feed.rss'},
    'trustwave': {'name': 'Trustwave SpiderLabs', 'url': 'https://www.trustwave.com/en-us/resources/blogs/spiderlabs-blog/rss.xml'},
    'welivesecurity_eset': {'name': 'We Live Security (ESET)', 'url': 'https://www.welivesecurity.com/en/rss/feed/'},
    'wiz': {'name': 'WIZ Blog', 'url': 'https://www.wiz.io/feed/rss.xml'},
    'wiz_threat': {'name': 'WIZ Cloud Threat Landscape', 'url': 'https://www.wiz.io/api/feed/cloud-threat-landscape/rss.xml'},
    'zimperium': {'name': 'Zimperium', 'url': 'https://www.zimperium.com/blog/feed/'},
    'zimperium_threat': {'name': 'Zimperium (Threat Research)', 'url': 'https://www.zimperium.com/blog-category/threat-research/feed/'},
    'volexity': {'name': 'Volexity', 'url': 'https://www.volexity.com/blog/feed/'},
}

# Get currently included feeds from cybersecurity_news.py
EXISTING_FEED_URLS = [
    'https://www.404media.co/rss/',
    'https://feeds.feedburner.com/TheHackersNews',
    'https://www.welivesecurity.com/en/rss/feed/',
    'https://www.darkreading.com/rss.xml',
    'https://www.bleepingcomputer.com/feed/',
    'https://www.malwarebytes.com/blog/feed/index.xml',
    'https://www.wired.com/category/security/feed',
    'https://www.eff.org/rss/updates.xml',
    'https://www.schneier.com/feed/atom/',
    'https://cyberscoop.com/feed/',
    'https://www.securityweek.com/feed/',
    'https://securityaffairs.com/feed',
    'https://databreaches.net/feed/',
    'https://aws.amazon.com/blogs/security/feed/',
    'https://www.crowdstrike.com/en-us/blog/feed',
    'https://www.tenable.com/blog/rss',
    'https://privacyinternational.org/rss.xml',
    'https://krebsonsecurity.com/feed/',
    'https://www.troyhunt.com/rss/',
    'https://grahamcluley.com/feed/',
    'https://nakedsecurity.sophos.com/feed/',
    'http://feeds.trendmicro.com/TrendMicroResearch',
    'https://feeds.feedburner.com/GoogleOnlineSecurityBlog',
    'https://www.ncsc.gov.uk/api/1/services/v1/all-rss-feed.xml',
    'https://threatpost.com/feed/',
    'https://www.infosecurity-magazine.com/rss/news/',
    'https://www.helpnetsecurity.com/feed/',
    'https://thecyberexpress.com/feed/',
    'https://cofense.com/feed/',
    'https://www.theguardian.com/technology/data-computer-security/rss',
    'https://www.cio.com/feed/',
    'https://feeds.feedburner.com/govtech/blogs/lohrmann_on_infrastructure',
    'https://feeds.feedburner.com/NoticeBored',
    'https://feeds.feedburner.com/ckdiii',
    'https://feeds.feedburner.com/eset/blog',
    'https://medium.com/feed/anton-on-security',
    'https://arstechnica.com/tag/security/feed/',
    'https://www.bellingcat.com/feed/',
    'https://www.hackmageddon.com/feed/',
    'https://www.hackread.com/feed/',
    'http://www.malware-traffic-analysis.net/blog-entries.rss',
    'http://www.techrepublic.com/rssfeeds/topic/security/?feedType=rssfeeds',
    'https://www.zdnet.com/topic/security/rss.xml',
    'https://blog.0patch.com/feeds/posts/default',
    'https://cybersecurity.att.com/site/blog-all-rss',
    'https://www.bitdefender.com/blog/api/rss/labs/',
    'https://sed-cms.broadcom.com/rss/v1/blogs/rss.xml',
    'https://blogs.cisco.com/security/feed',
    'http://feeds.feedburner.com/feedburner/Talos',
    'https://blog.cloudflare.com/tag/security/rss',
    'https://blog.eclecticiq.com/rss.xml',
    'https://blog.fox-it.com/feed/',
    'https://googleprojectzero.blogspot.com/feeds/posts/default',
    'https://www.microsoft.com/security/blog/feed/',
    'https://www.proofpoint.com/us/rss.xml',
    'https://blog.quarkslab.com/feeds/all.rss.xml',
    'https://blogs.quickheal.com/feed/',
    'https://therecord.media/feed/',
    'https://sensepost.com/rss.xml',
    'https://www.sentinelone.com/labs/feed/',
    'https://socprime.com/blog/feed/',
    'https://www.tripwire.com/state-of-security/feed/',
    'https://www.upguard.com/news/rss.xml',
    'https://www.upguard.com/breaches/rss.xml',
    'https://www.virusbulletin.com/rss',
    'https://blog.virustotal.com/feeds/posts/default',
]


async def test_feed(key: str, feed_data: dict) -> dict:
    """Test a single RSS feed."""
    result = {
        'key': key,
        'name': feed_data['name'],
        'url': feed_data['url'],
        'status': 'unknown',
        'error': None,
        'items': 0
    }
    
    try:
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(feed_data['url']) as response:
                result['status'] = response.status
                
                if response.status != 200:
                    result['error'] = f"HTTP {response.status}"
                    return result
                
                content = await response.text()
                
                try:
                    root = ET.fromstring(content)
                    items = root.findall('.//{http://www.w3.org/2005/Atom}entry')
                    if not items:
                        items = root.findall('.//item')
                    
                    result['items'] = len(items)
                    
                    if items:
                        result['status'] = 'working'
                    else:
                        result['error'] = 'No items found'
                        result['status'] = 'empty'
                
                except ET.ParseError as e:
                    result['error'] = f"XML parse error"
                    result['status'] = 'invalid'
    
    except asyncio.TimeoutError:
        result['error'] = 'Timeout'
        result['status'] = 'timeout'
    except Exception as e:
        result['error'] = f"{type(e).__name__}"
        result['status'] = 'error'
    
    return result


async def main():
    """Test all feeds."""
    print("=" * 80)
    print("COMPREHENSIVE CYBERSECURITY FEED ANALYSIS")
    print("=" * 80)
    print()
    
    # Check already included
    print("📋 CHECKING FOR ALREADY INCLUDED FEEDS...")
    print("-" * 80)
    already_included = []
    
    for key, feed in COMPREHENSIVE_FEEDS.items():
        url_normalized = feed['url'].lower().replace('https://', '').replace('http://', '').rstrip('/')
        
        for existing_url in EXISTING_FEED_URLS:
            existing_normalized = existing_url.lower().replace('https://', '').replace('http://', '').rstrip('/')
            
            if url_normalized == existing_normalized or url_normalized in existing_normalized or existing_normalized in url_normalized:
                already_included.append(key)
                print(f"✓ {feed['name']}")
                break
    
    print(f"\nTotal already included: {len(already_included)}")
    print()
    
    # Test missing feeds
    missing_feeds = {k: v for k, v in COMPREHENSIVE_FEEDS.items() if k not in already_included}
    
    print(f"🔍 TESTING {len(missing_feeds)} MISSING FEEDS...")
    print("-" * 80)
    print("This may take a few minutes...\n")
    
    # Test in batches of 20 for stability
    batch_size = 20
    all_results = []
    
    feed_items = list(missing_feeds.items())
    for i in range(0, len(feed_items), batch_size):
        batch = feed_items[i:i+batch_size]
        print(f"Testing batch {i//batch_size + 1}/{(len(feed_items)-1)//batch_size + 1}...")
        
        tasks = [test_feed(k, v) for k, v in batch]
        results = await asyncio.gather(*tasks)
        all_results.extend(results)
        
        await asyncio.sleep(1)  # Brief pause between batches
    
    # Categorize results
    working = [r for r in all_results if r['status'] == 'working']
    broken = [r for r in all_results if r['status'] != 'working']
    
    # Display working feeds
    print("\n✅ WORKING FEEDS (ready to add):")
    print("-" * 80)
    for r in sorted(working, key=lambda x: x['name']):
        print(f"✓ {r['name']:<50} [{r['items']:>3} items]")
    
    print(f"\nTotal working: {len(working)}")
    
    # Display broken feeds
    if broken:
        print("\n❌ NON-WORKING FEEDS:")
        print("-" * 80)
        for r in sorted(broken, key=lambda x: x['name']):
            print(f"✗ {r['name']:<50} [{r['status']}] {r['error'] or ''}")
        
        print(f"\nTotal non-working: {len(broken)}")
    
    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY:")
    print(f"  Already included: {len(already_included)}")
    print(f"  Working (can add): {len(working)}")
    print(f"  Non-working: {len(broken)}")
    print(f"  Total feeds analyzed: {len(COMPREHENSIVE_FEEDS)}")
    print("=" * 80)
    
    # Save results to file
    output = {
        'already_included': already_included,
        'working': [{'key': r['key'], 'name': r['name'], 'url': r['url'], 'items': r['items']} for r in working],
        'broken': [{'key': r['key'], 'name': r['name'], 'url': r['url'], 'status': r['status'], 'error': r['error']} for r in broken]
    }
    
    with open('comprehensive_feed_results.json', 'w') as f:
        json.dump(output, f, indent=2)
    
    print("\n📄 Results saved to: comprehensive_feed_results.json")


if __name__ == '__main__':
    asyncio.run(main())
