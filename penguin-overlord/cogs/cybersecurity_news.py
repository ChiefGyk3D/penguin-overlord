# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Cybersecurity News Cog - Aggregates cybersecurity and threat intelligence news.
"""

import logging
import discord
from discord.ext import commands, tasks
from discord import app_commands
import aiohttp
import re
import json
import os
from datetime import datetime
from html import unescape
import xml.etree.ElementTree as ET

logger = logging.getLogger(__name__)


NEWS_SOURCES = {
    '404media': {
        'name': '404 Media',
        'url': 'https://www.404media.co/rss/',
        'color': 0xFF6B35,
        'icon': '📰'
    },
    'thehackernews': {
        'name': 'The Hacker News',
        'url': 'https://feeds.feedburner.com/TheHackersNews',
        'color': 0xD9231F,
        'icon': '🔒'
    },
    'welivesecurity': {
        'name': 'WeLiveSecurity (ESET)',
        'url': 'https://www.welivesecurity.com/en/rss/feed/',
        'color': 0x00A3E0,
        'icon': '🛡️'
    },
    'darkreading': {
        'name': 'Dark Reading',
        'url': 'https://www.darkreading.com/rss.xml',
        'color': 0x1A1A1A,
        'icon': '🌑'
    },
    'bleepingcomputer': {
        'name': 'BleepingComputer',
        'url': 'https://www.bleepingcomputer.com/feed/',
        'color': 0x0066CC,
        'icon': '💻'
    },
    'malwarebytes': {
        'name': 'Malwarebytes Labs',
        'url': 'https://www.malwarebytes.com/blog/feed/index.xml',
        'color': 0xFF6A13,
        'icon': '🦠'
    },
    'wired_security': {
        'name': 'Wired Security',
        'url': 'https://www.wired.com/category/security/feed',
        'color': 0x000000,
        'icon': '📡'
    },
    'eff': {
        'name': 'EFF Deeplinks',
        'url': 'https://www.eff.org/rss/updates.xml',
        'color': 0xC8102E,
        'icon': '🗽'
    },
    'schneier': {
        'name': 'Schneier on Security',
        'url': 'https://www.schneier.com/feed/atom/',
        'color': 0x8B4513,
        'icon': '📚'
    },
    'cyberscoop': {
        'name': 'CyberScoop',
        'url': 'https://cyberscoop.com/feed/',
        'color': 0x1E3A8A,
        'icon': '🏛️'
    },
    'securityweek': {
        'name': 'SecurityWeek',
        'url': 'https://www.securityweek.com/feed/',
        'color': 0x2E5C8A,
        'icon': '📊'
    },
    'securityaffairs': {
        'name': 'Security Affairs',
        'url': 'https://securityaffairs.com/feed',
        'color': 0xC41E3A,
        'icon': '🔐'
    },
    'databreaches': {
        'name': 'DataBreaches.net',
        'url': 'https://databreaches.net/feed/',
        'color': 0xE74C3C,
        'icon': '💥'
    },
    'aws_security': {
        'name': 'AWS Security Blog',
        'url': 'https://aws.amazon.com/blogs/security/feed/',
        'color': 0xFF9900,
        'icon': '☁️'
    },
    'crowdstrike': {
        'name': 'CrowdStrike',
        'url': 'https://www.crowdstrike.com/en-us/blog/feed',
        'color': 0xE01F3D,
        'icon': '🦅'
    },
    'tenable': {
        'name': 'Tenable',
        'url': 'https://www.tenable.com/blog/rss',
        'color': 0x00B2A9,
        'icon': '🔬'
    },
    'privacyintl': {
        'name': 'Privacy International',
        'url': 'https://privacyinternational.org/rss.xml',
        'color': 0x9B59B6,
        'icon': '🕵️‍♀️'
    },
    'krebs': {
        'name': 'Krebs on Security',
        'url': 'https://krebsonsecurity.com/feed/',
        'color': 0x2C3E50,
        'icon': '🔒'
    },
    'troyhunt': {
        'name': 'Troy Hunt',
        'url': 'https://www.troyhunt.com/rss/',
        'color': 0x3498DB,
        'icon': '🔐'
    },
    'grahamcluley': {
        'name': 'Graham Cluley',
        'url': 'https://grahamcluley.com/feed/',
        'color': 0xE67E22,
        'icon': '🛡️'
    },
    'sophos': {
        'name': 'Naked Security (Sophos)',
        'url': 'https://nakedsecurity.sophos.com/feed/',
        'color': 0x0080C9,
        'icon': '🔒'
    },
    'trendmicro': {
        'name': 'Trend Micro Research',
        'url': 'http://feeds.trendmicro.com/TrendMicroResearch',
        'color': 0xD71920,
        'icon': '🔬'
    },
    'google_security': {
        'name': 'Google Security Blog',
        'url': 'https://feeds.feedburner.com/GoogleOnlineSecurityBlog',
        'color': 0x4285F4,
        'icon': '🔐'
    },
    'ncsc_uk': {
        'name': 'NCSC (UK)',
        'url': 'https://www.ncsc.gov.uk/api/1/services/v1/all-rss-feed.xml',
        'color': 0x003366,
        'icon': '🇬🇧'
    },
    'threatpost': {
        'name': 'Threatpost',
        'url': 'https://threatpost.com/feed/',
        'color': 0xC0392B,
        'icon': '⚠️'
    },
    'infosecurity_mag': {
        'name': 'Infosecurity Magazine',
        'url': 'https://www.infosecurity-magazine.com/rss/news/',
        'color': 0x16A085,
        'icon': '📰'
    },
    'helpnetsecurity': {
        'name': 'Help Net Security',
        'url': 'https://www.helpnetsecurity.com/feed/',
        'color': 0x2980B9,
        'icon': '🛡️'
    },
    'cyberexpress': {
        'name': 'The Cyber Express',
        'url': 'https://thecyberexpress.com/feed/',
        'color': 0x8E44AD,
        'icon': '📡'
    },
    'cofense': {
        'name': 'Cofense',
        'url': 'https://cofense.com/feed/',
        'color': 0xF39C12,
        'icon': '📧'
    },
    'guardian_security': {
        'name': 'The Guardian - Security',
        'url': 'https://www.theguardian.com/technology/data-computer-security/rss',
        'color': 0x052962,
        'icon': '📰'
    },
    'cio_security': {
        'name': 'CIO',
        'url': 'https://www.cio.com/feed/',
        'color': 0x1E8BC3,
        'icon': '💼'
    },
    'govtech_lohrmann': {
        'name': 'GovTech - Lohrmann on Security',
        'url': 'https://feeds.feedburner.com/govtech/blogs/lohrmann_on_infrastructure',
        'color': 0x34495E,
        'icon': '🏛️'
    },
    'noticebored': {
        'name': 'ISO27k Infosec Blog',
        'url': 'https://feeds.feedburner.com/NoticeBored',
        'color': 0x7F8C8D,
        'icon': '📋'
    },
    'ckdiii': {
        'name': 'CK\'s Technology News',
        'url': 'https://feeds.feedburner.com/ckdiii',
        'color': 0x95A5A6,
        'icon': '📡'
    },
    'eset_blog': {
        'name': 'ESET Blog',
        'url': 'https://feeds.feedburner.com/eset/blog',
        'color': 0x00A3E0,
        'icon': '🛡️'
    },
    'anton_on_security': {
        'name': 'Anton on Security',
        'url': 'https://medium.com/feed/anton-on-security',
        'color': 0x00AB6C,
        'icon': '✍️'
    },
    'arstechnica_security': {
        'name': 'Ars Technica (Security)',
        'url': 'https://arstechnica.com/tag/security/feed/',
        'color': 0xFF4E00,
        'icon': '🔬'
    },
    'bellingcat': {
        'name': 'bellingcat',
        'url': 'https://www.bellingcat.com/feed/',
        'color': 0x0099CC,
        'icon': '🔍'
    },
    'hackmageddon': {
        'name': 'HACKMAGEDDON',
        'url': 'https://www.hackmageddon.com/feed/',
        'color': 0x8B0000,
        'icon': '💣'
    },
    'hackread': {
        'name': 'HackRead',
        'url': 'https://www.hackread.com/feed/',
        'color': 0xE91E63,
        'icon': '📖'
    },
    'malware_traffic': {
        'name': 'Malware Traffic Analysis',
        'url': 'http://www.malware-traffic-analysis.net/blog-entries.rss',
        'color': 0x9C27B0,
        'icon': '🔬'
    },
    'techrepublic_security': {
        'name': 'TechRepublic (security)',
        'url': 'http://www.techrepublic.com/rssfeeds/topic/security/?feedType=rssfeeds',
        'color': 0x0066CC,
        'icon': '💼'
    },
    'zdnet_security': {
        'name': 'ZDNet (security)',
        'url': 'https://www.zdnet.com/topic/security/rss.xml',
        'color': 0xED1C24,
        'icon': '🔐'
    },
    'zeropatch': {
        'name': '0patch Blog',
        'url': 'https://blog.0patch.com/feeds/posts/default',
        'color': 0x00BCD4,
        'icon': '🩹'
    },
    'att_cybersecurity': {
        'name': 'AT&T Cybersecurity',
        'url': 'https://cybersecurity.att.com/site/blog-all-rss',
        'color': 0x00A8E0,
        'icon': '📱'
    },
    'bitdefender_labs': {
        'name': 'Bitdefender Labs',
        'url': 'https://www.bitdefender.com/blog/api/rss/labs/',
        'color': 0xED1C24,
        'icon': '🛡️'
    },
    'broadcom_symantec': {
        'name': 'Broadcom Symantec',
        'url': 'https://sed-cms.broadcom.com/rss/v1/blogs/rss.xml',
        'color': 0xCC092F,
        'icon': '🔒'
    },
    'cisco_security': {
        'name': 'Cisco Security Blog',
        'url': 'https://blogs.cisco.com/security/feed',
        'color': 0x049FD9,
        'icon': '🔧'
    },
    'cisco_talos': {
        'name': 'Cisco Talos Intelligence',
        'url': 'http://feeds.feedburner.com/feedburner/Talos',
        'color': 0x1BA0D7,
        'icon': '🎯'
    },
    'cloudflare_security': {
        'name': 'Cloudflare Security',
        'url': 'https://blog.cloudflare.com/tag/security/rss',
        'color': 0xF38020,
        'icon': '☁️'
    },
    'eclecticiq': {
        'name': 'EclecticIQ',
        'url': 'https://blog.eclecticiq.com/rss.xml',
        'color': 0x00A5E3,
        'icon': '🔍'
    },
    'foxit': {
        'name': 'Fox-IT International',
        'url': 'https://blog.fox-it.com/feed/',
        'color': 0xFF6600,
        'icon': '🦊'
    },
    'google_project_zero': {
        'name': 'Google Project Zero',
        'url': 'https://googleprojectzero.blogspot.com/feeds/posts/default',
        'color': 0xEA4335,
        'icon': '0️⃣'
    },
    'microsoft_security': {
        'name': 'Microsoft Security Blog',
        'url': 'https://www.microsoft.com/security/blog/feed/',
        'color': 0x00A4EF,
        'icon': '🪟'
    },
    'proofpoint': {
        'name': 'Proofpoint',
        'url': 'https://www.proofpoint.com/us/rss.xml',
        'color': 0x5E3D99,
        'icon': '📧'
    },
    'quarkslab': {
        'name': 'Quarkslab',
        'url': 'https://blog.quarkslab.com/feeds/all.rss.xml',
        'color': 0x6A1B9A,
        'icon': '⚛️'
    },
    'quickheal': {
        'name': 'Quick Heal Antivirus',
        'url': 'https://blogs.quickheal.com/feed/',
        'color': 0xE31E24,
        'icon': '💊'
    },
    'therecord': {
        'name': 'The Record',
        'url': 'https://therecord.media/feed/',
        'color': 0x000000,
        'icon': '🎙️'
    },
    'sensepost': {
        'name': 'SensePost (Orange)',
        'url': 'https://sensepost.com/rss.xml',
        'color': 0xFF7900,
        'icon': '🍊'
    },
    'sentinelone': {
        'name': 'SentinelOne Labs',
        'url': 'https://www.sentinelone.com/labs/feed/',
        'color': 0x5D00D3,
        'icon': '🔬'
    },
    'socprime': {
        'name': 'SOC Prime',
        'url': 'https://socprime.com/blog/feed/',
        'color': 0x0066CC,
        'icon': '🎯'
    },
    'tripwire': {
        'name': 'Tripwire',
        'url': 'https://www.tripwire.com/state-of-security/feed/',
        'color': 0xD32F2F,
        'icon': '🚨'
    },
    'upguard_news': {
        'name': 'UpGuard News',
        'url': 'https://www.upguard.com/news/rss.xml',
        'color': 0x4A90E2,
        'icon': '📰'
    },
    'upguard_breaches': {
        'name': 'UpGuard Breaches',
        'url': 'https://www.upguard.com/breaches/rss.xml',
        'color': 0xE53935,
        'icon': '💥'
    },
    'virusbulletin': {
        'name': 'Virus Bulletin',
        'url': 'https://www.virusbulletin.com/rss',
        'color': 0x8BC34A,
        'icon': '📋'
    },
    'virustotal': {
        'name': 'VirusTotal',
        'url': 'https://blog.virustotal.com/feeds/posts/default',
        'color': 0x394EFF,
        'icon': '🔬'
    },
    'cybersecuritynews': {
        'name': 'Cyber Security News',
        'url': 'https://cybersecuritynews.com/feed/',
        'color': 0x1E88E5,
        'icon': '🛡️'
    },
    'gbhackers': {
        'name': 'GBHackers',
        'url': 'https://gbhackers.com/feed/',
        'color': 0xE53935,
        'icon': '🔐'
    },
    'securityboulevard': {
        'name': 'Security Boulevard',
        'url': 'https://securityboulevard.com/feed/',
        'color': 0x43A047,
        'icon': '🛡️'
    },
    'thecyberwire': {
        'name': 'The Cyber Wire',
        'url': 'https://thecyberwire.com/feeds/rss.xml',
        'color': 0xFB8C00,
        'icon': '📻'
    },
    'theregister_security': {
        'name': 'The Register (Security)',
        'url': 'https://www.theregister.com/security/headlines.atom',
        'color': 0x8E24AA,
        'icon': '📰'
    },
    'techcrunch_security': {
        'name': 'TechCrunch (Security)',
        'url': 'https://techcrunch.com/category/security/feed/',
        'color': 0x00897B,
        'icon': '🚀'
    },
    'nextgov_cyber': {
        'name': 'NextGov (Cybersecurity)',
        'url': 'https://www.nextgov.com/rss/cybersecurity/',
        'color': 0x3949AB,
        'icon': '🏛️'
    },
    'securityledger': {
        'name': 'The Security Ledger',
        'url': 'https://feeds.feedblitz.com/thesecurityledger&x=1',
        'color': 0xD81B60,
        'icon': '📖'
    },
    'mandiant': {
        'name': 'Mandiant',
        'url': 'https://www.mandiant.com/resources/blog/rss.xml',
        'color': 0x00ACC1,
        'icon': '🔥'
    },
    'datadog_security': {
        'name': 'Datadog Security Labs',
        'url': 'https://securitylabs.datadoghq.com/rss/feed.xml',
        'color': 0xC0CA33,
        'icon': '🐕'
    },
    'github_security': {
        'name': 'GitHub Security Lab',
        'url': 'https://github.blog/tag/github-security-lab/feed/',
        'color': 0x6D4C41,
        'icon': '🐙'
    },
    'google_tag': {
        'name': 'Google Threat Analysis Group',
        'url': 'https://blog.google/threat-analysis-group/rss/',
        'color': 0x546E7A,
        'icon': '🔍'
    },
    'greynoise': {
        'name': 'GreyNoise Labs',
        'url': 'https://www.labs.greynoise.io/grimoire/index.xml',
        'color': 0xF4511E,
        'icon': '📡'
    },
    'groupib': {
        'name': 'Group IB',
        'url': 'https://blog.group-ib.com/rss.xml',
        'color': 0x7CB342,
        'icon': '🛡️'
    },
    'haveibeenpwned': {
        'name': 'Have I Been Pwned',
        'url': 'https://feeds.feedburner.com/HaveIBeenPwnedLatestBreaches',
        'color': 0x5E35B1,
        'icon': '💔'
    },
    'huntress': {
        'name': 'Huntress',
        'url': 'https://www.huntress.com/blog/rss.xml',
        'color': 0x039BE5,
        'icon': '🎯'
    },
    'paloalto_unit42_feed': {
        'name': 'PaloAlto Unit 42',
        'url': 'http://feeds.feedburner.com/Unit42',
        'color': 0xE91E63,
        'icon': '🔬'
    },
    'recorded_future': {
        'name': 'Recorded Future',
        'url': 'https://www.recordedfuture.com/feed',
        'color': 0x00897B,
        'icon': '🔮'
    },
    'wiz': {
        'name': 'WIZ Blog',
        'url': 'https://www.wiz.io/feed/rss.xml',
        'color': 0xFF5722,
        'icon': '☁️'
    },
    'wiz_threat': {
        'name': 'WIZ Cloud Threat Landscape',
        'url': 'https://www.wiz.io/api/feed/cloud-threat-landscape/rss.xml',
        'color': 0x9C27B0,
        'icon': '⛈️'
    },
    'cybereason': {
        'name': 'Cybereason',
        'url': 'https://www.cybereason.com/blog/rss.xml',
        'color': 0x1E88E5,
        'icon': '🕵️'
    },
    'sekoia': {
        'name': 'Sekoia',
        'url': 'https://blog.sekoia.io/feed/',
        'color': 0xE53935,
        'icon': '🛡️'
    },
    'trustwave': {
        'name': 'Trustwave SpiderLabs',
        'url': 'https://www.trustwave.com/en-us/resources/blogs/spiderlabs-blog/rss.xml',
        'color': 0x43A047,
        'icon': '🕷️'
    },
    'ahnlab': {
        'name': 'AhnLab Security Intelligence',
        'url': 'https://asec.ahnlab.com/en/feed/',
        'color': 0xFB8C00,
        'icon': '🕵️'
    },
    'checkmarx': {
        'name': 'Checkmarx',
        'url': 'https://medium.com/feed/checkmarx-security',
        'color': 0x8E24AA,
        'icon': '✓'
    },
    'anyrun_malware': {
        'name': 'ANY.RUN (Malware Analysis)',
        'url': 'https://any.run/cybersecurity-blog/category/malware-analysis/feed/',
        'color': 0x00897B,
        'icon': '🦠'
    },
    'blackhills_blue': {
        'name': 'Black Hills (Blue Team)',
        'url': 'https://www.blackhillsinfosec.com/category/blue-team/feed/',
        'color': 0x3949AB,
        'icon': '💙'
    },
    'fortinet_threat_feed': {
        'name': 'Fortinet (Threat Research)',
        'url': 'https://feeds.fortinet.com/fortinet/blog/threat-research&x=1',
        'color': 0xD81B60,
        'icon': '⚠️'
    },
    'cis_advisory': {
        'name': 'CIS (Advisories)',
        'url': 'https://www.cisecurity.org/feed/advisories',
        'color': 0x00ACC1,
        'icon': '📋'
    },
    'pulsedive': {
        'name': 'Pulsedive',
        'url': 'https://blog.pulsedive.com/rss/',
        'color': 0xC0CA33,
        'icon': '📡'
    },
    'alexplaskett': {
        'name': 'Alex Plaskett',
        'url': 'https://alexplaskett.github.io/feed',
        'color': 0x1E88E5,
        'icon': '🔍'
    },
    'blazesec': {
        'name': "Blaze's Security Blog",
        'url': 'https://bartblaze.blogspot.com/feeds/posts/default',
        'color': 0xE53935,
        'icon': '🛡️'
    },
    'bushidotoken': {
        'name': 'BushidoToken Threat Intel',
        'url': 'https://blog.bushidotoken.net/feeds/posts/default',
        'color': 0x43A047,
        'icon': '🔐'
    },
    'connormcgarr': {
        'name': 'Connor McGarr',
        'url': 'https://connormcgarr.github.io/feed',
        'color': 0xFB8C00,
        'icon': '⚠️'
    },
    'curatedintel': {
        'name': 'Curated Intelligence',
        'url': 'https://www.curatedintel.org/feeds/posts/default',
        'color': 0x8E24AA,
        'icon': '🦠'
    },
    'cyberintelinsights': {
        'name': 'Cyber Intelligence Insights',
        'url': 'https://intelinsights.substack.com/feed',
        'color': 0x00897B,
        'icon': '📊'
    },
    'cybercrimediaries': {
        'name': 'Cybercrime Diaries',
        'url': 'https://www.cybercrimediaries.com/blog-feed.xml',
        'color': 0x3949AB,
        'icon': '🕵️'
    },
    'darknet': {
        'name': 'Darknet',
        'url': 'http://www.darknet.org.uk/feed/',
        'color': 0xD81B60,
        'icon': '💻'
    },
    'databreaches': {
        'name': 'DataBreaches',
        'url': 'https://www.databreaches.net/feed/',
        'color': 0x00ACC1,
        'icon': '🚨'
    },
    'doublepulsar': {
        'name': 'DoublePulsar (Kevin Beaumont)',
        'url': 'https://doublepulsar.com/feed',
        'color': 0xC0CA33,
        'icon': '📡'
    },
    'krebsonsecurity': {
        'name': 'Krebs on Security',
        'url': 'http://krebsonsecurity.com/feed/',
        'color': 0x6D4C41,
        'icon': '🔬'
    },
    'krebs_breaches': {
        'name': 'Krebs on Security (Data Breaches)',
        'url': 'https://krebsonsecurity.com/category/data-breaches/feed/',
        'color': 0x546E7A,
        'icon': '🎯'
    },
    'krebs_warnings': {
        'name': 'Krebs on Security (Latest Warnings)',
        'url': 'https://krebsonsecurity.com/category/latest-warnings/feed/',
        'color': 0xF4511E,
        'icon': '📰'
    },
    'krebs_ransomware': {
        'name': 'Krebs on Security (Ransomware)',
        'url': 'https://krebsonsecurity.com/category/ransomware/feed/',
        'color': 0x7CB342,
        'icon': '🧪'
    },
    'lohrmann': {
        'name': 'Lohrmann on Cybersecurity',
        'url': 'http://feeds.feedburner.com/govtech/blogs/lohrmann_on_infrastructure',
        'color': 0x5E35B1,
        'icon': '🔓'
    },
    'lowleveladventures': {
        'name': 'Low-level adventures',
        'url': 'https://0x434b.dev/rss/',
        'color': 0x039BE5,
        'icon': '💾'
    },
    'n1ghtwolf': {
        'name': 'n1ght-w0lf',
        'url': 'https://n1ght-w0lf.github.io/feed',
        'color': 0xE91E63,
        'icon': '🌐'
    },
    'naosec': {
        'name': 'nao_sec',
        'url': 'https://nao-sec.org/feed',
        'color': 0xFF5722,
        'icon': '⚡'
    },
    'outflux': {
        'name': 'Outflux',
        'url': 'https://outflux.net/blog/feed/',
        'color': 0x9C27B0,
        'icon': '🔑'
    },
    'breachescloud': {
        'name': 'Public Cloud Security Breaches',
        'url': 'https://www.breaches.cloud/index.xml',
        'color': 0x1976D2,
        'icon': '📚'
    },
    'schneier': {
        'name': 'Schneier on Security',
        'url': 'https://www.schneier.com/blog/atom.xml',
        'color': 0x1E88E5,
        'icon': '🔍'
    },
    'dfirreport': {
        'name': 'The DFIR Report',
        'url': 'https://thedfirreport.com/feed/',
        'color': 0xE53935,
        'icon': '🛡️'
    },
    'troyhunt_scam': {
        'name': 'Troy Hunt (Scam)',
        'url': 'https://www.troyhunt.com/tag/scam/rss/',
        'color': 0x43A047,
        'icon': '🔐'
    },
    'troyhunt_security': {
        'name': 'Troy Hunt (Security)',
        'url': 'https://www.troyhunt.com/tag/security/rss/',
        'color': 0xFB8C00,
        'icon': '⚠️'
    },
    'willsroot': {
        'name': "Will's Root",
        'url': 'https://www.willsroot.io/feeds/posts/default',
        'color': 0x8E24AA,
        'icon': '🦠'
    },
    'citizenlab': {
        'name': 'Citizen Lab',
        'url': 'https://citizenlab.ca/feed/',
        'color': 0x00897B,
        'icon': '📊'
    },
    'isc_sans': {
        'name': "ISC Handler's Diary",
        'url': 'https://isc.sans.edu/rssfeed_full.xml',
        'color': 0x3949AB,
        'icon': '🕵️'
    },
    'reddit_cybersecurity': {
        'name': 'Reddit (/r/cybersecurity)',
        'url': 'https://www.reddit.com/r/cybersecurity/.rss',
        'color': 0xD81B60,
        'icon': '💻'
    },
    'reddit_netsec': {
        'name': 'Reddit (/r/netsec)',
        'url': 'http://www.reddit.com/r/netsec/.rss',
        'color': 0x00ACC1,
        'icon': '🚨'
    },
    'zdi_published': {
        'name': 'Zero Day Initiative (Published)',
        'url': 'https://www.zerodayinitiative.com/rss/published/',
        'color': 0xC0CA33,
        'icon': '📡'
    },
    'cisa_analysis': {
        'name': 'CISA Analysis Reports',
        'url': 'https://us-cert.cisa.gov/ncas/analysis-reports.xml',
        'color': 0x004B87,
        'icon': '🔬'
    }
}


class CybersecurityNews(commands.Cog):
    """Cybersecurity news aggregator and poster."""
    
    NEWS_SOURCES = NEWS_SOURCES
    
    def __init__(self, bot):
        self.bot = bot
        self.session = None
        self.state_file = 'data/cybersecurity_news_state.json'
        self.state = self._load_state()
        self.news_auto_poster.start()
    
    def cog_unload(self):
        self.news_auto_poster.cancel()
        if self.session:
            self.bot.loop.create_task(self.session.close())
    
    async def cog_load(self):
        self.session = aiohttp.ClientSession()
    
    def _load_state(self) -> dict:
        """Load state from file."""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load cybersecurity news state: {e}")
        
        return {
            'last_posted': {},
            'last_check': None
        }
    
    def _save_state(self):
        """Save state to file."""
        try:
            os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
            with open(self.state_file, 'w') as f:
                json.dump(self.state, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save cybersecurity news state: {e}")
    
    async def _fetch_rss_feed(self, source_key: str) -> tuple[str, str, str]:
        """Fetch latest article from an RSS feed."""
        source = NEWS_SOURCES.get(source_key)
        if not source:
            return None, None, None
        
        try:
            if not self.session:
                self.session = aiohttp.ClientSession()
            
            async with self.session.get(source['url'], timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status != 200:
                    logger.warning(f"Failed to fetch {source['name']}: HTTP {response.status}")
                    return None, None, None
                
                content = await response.text()
                
                # Parse RSS/Atom feed using proper XML parser
                # This handles item tags with attributes (e.g., <item rdf:about="...">)
                try:
                    root = ET.fromstring(content)
                except ET.ParseError as e:
                    logger.warning(f"XML parse error for {source['name']}: {e}")
                    return None, None, None
                
                # Find items (supports both <item> and <entry> tags)
                items = root.findall('.//{http://www.w3.org/2005/Atom}entry')
                if not items:
                    items = root.findall('.//item')
                
                if not items:
                    return None, None, None
                
                item = items[0]
                
                # Extract title
                title_elem = item.find('.//{http://www.w3.org/2005/Atom}title')
                if title_elem is None:
                    title_elem = item.find('title')
                title = unescape(title_elem.text.strip()) if title_elem is not None and title_elem.text else "No title"
                
                # Extract link
                link_elem = item.find('.//{http://www.w3.org/2005/Atom}link')
                if link_elem is not None and 'href' in link_elem.attrib:
                    link = link_elem.attrib['href'].strip()
                else:
                    link_elem = item.find('link')
                    link = link_elem.text.strip() if link_elem is not None and link_elem.text else source['url']
                
                # Extract description
                desc_elem = item.find('.//{http://www.w3.org/2005/Atom}summary')
                if desc_elem is None:
                    desc_elem = item.find('description')
                
                description = ""
                if desc_elem is not None and desc_elem.text:
                    desc = desc_elem.text.strip()
                    desc = re.sub(r'<[^>]+>', '', desc)  # Strip HTML
                    desc = unescape(desc)
                    description = desc[:300] + "..." if len(desc) > 300 else desc
                
                return title, link, description
        
        except Exception as e:
            logger.error(f"Error fetching {source['name']}: {e}")
            return None, None, None
    
    @tasks.loop(hours=4)
    async def news_auto_poster(self):
        """Automatically post cybersecurity news."""
        try:
            manager = self.bot.get_cog('NewsManager')
            if not manager:
                return
            
            config = manager.get_category_config('cybersecurity')
            
            if not config.get('enabled'):
                return
            
            channel_id = config.get('channel_id')
            if not channel_id:
                return
            
            channel = self.bot.get_channel(channel_id)
            if not channel:
                return
            
            # Update interval dynamically
            interval = config.get('interval_hours', 4)
            if interval != self.news_auto_poster.hours:
                self.news_auto_poster.change_interval(hours=interval)
            
            # Post from each enabled source
            for source_key in NEWS_SOURCES.keys():
                if not manager.is_source_enabled('cybersecurity', source_key):
                    continue
                
                title, link, description = await self._fetch_rss_feed(source_key)
                
                if not title or not link:
                    continue
                
                # Check if already posted
                if self.state['last_posted'].get(source_key) == link:
                    continue
                
                source = NEWS_SOURCES[source_key]
                
                embed = discord.Embed(
                    title=f"{source['icon']} {title}",
                    url=link,
                    description=description,
                    color=source['color'],
                    timestamp=datetime.utcnow()
                )
                embed.set_footer(text=f"Source: {source['name']}")
                
                try:
                    await channel.send(embed=embed)
                    self.state['last_posted'][source_key] = link
                    self._save_state()
                except Exception as e:
                    logger.error(f"Failed to post from {source['name']}: {e}")
        
        except Exception as e:
            logger.error(f"Error in cybersecurity news auto-poster: {e}")
    
    @news_auto_poster.before_loop
    async def before_news_auto_poster(self):
        await self.bot.wait_until_ready()
        if not self.session:
            self.session = aiohttp.ClientSession()
    
    @app_commands.command(name="cybersecurity", description="Fetch latest cybersecurity news from a specific source")
    @app_commands.describe(source="News source to fetch from")
    async def cybersecurity_news(self, interaction: discord.Interaction, source: str):
        """Manually fetch news from a specific source."""
        if source not in NEWS_SOURCES:
            await interaction.response.send_message(
                f"❌ Unknown source. Use `/news list_sources cybersecurity` to see available sources.",
                ephemeral=True
            )
            return
        
        await interaction.response.defer(thinking=True)
        
        title, link, description = await self._fetch_rss_feed(source)
        
        if not title:
            await interaction.followup.send("❌ Failed to fetch news from this source.")
            return
        
        source_info = NEWS_SOURCES[source]
        
        embed = discord.Embed(
            title=f"{source_info['icon']} {title}",
            url=link,
            description=description,
            color=source_info['color'],
            timestamp=datetime.utcnow()
        )
        embed.set_footer(text=f"Source: {source_info['name']}")
        
        await interaction.followup.send(embed=embed)


async def setup(bot):
    await bot.add_cog(CybersecurityNews(bot))
    logger.info("Cybersecurity News cog loaded")
