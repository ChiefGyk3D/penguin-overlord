# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Tech Quote Cog - Daily quotes from tech legends.
"""

import logging
import random
import discord
from discord.ext import commands
from discord.ui import View, Button

logger = logging.getLogger(__name__)


# Tech quotes database with attribution and bios
TECH_QUOTES = [
    {
        "quote": "Talk is cheap. Show me the code.",
        "author": "Linus Torvalds",
        "bio": "Creator of Linux and Git",
        "wiki": "https://en.wikipedia.org/wiki/Linus_Torvalds",
        "color": 0xFCC624  # Linux yellow
    },
    {
        "quote": "Free software is a matter of liberty, not price. To understand the concept, you should think of 'free' as in 'free speech,' not as in 'free beer.'",
        "author": "Richard Stallman",
        "bio": "Founder of GNU Project and Free Software Foundation",
        "wiki": "https://en.wikipedia.org/wiki/Richard_Stallman",
        "color": 0xA42E2B  # GNU red
    },
    {
        "quote": "The most dangerous phrase in the language is, 'We've always done it this way.'",
        "author": "Grace Hopper",
        "bio": "Computer programming pioneer and inventor of the first compiler",
        "wiki": "https://en.wikipedia.org/wiki/Grace_Hopper",
        "color": 0x9B59B6  # Purple
    },
    {
        "quote": "Programs must be written for people to read, and only incidentally for machines to execute.",
        "author": "Harold Abelson",
        "bio": "Computer scientist and professor at MIT",
        "wiki": "https://en.wikipedia.org/wiki/Hal_Abelson",
        "color": 0x3498DB  # Blue
    },
    {
        "quote": "The best way to predict the future is to invent it.",
        "author": "Alan Kay",
        "bio": "Computer scientist and pioneer of object-oriented programming",
        "wiki": "https://en.wikipedia.org/wiki/Alan_Kay",
        "color": 0xE67E22  # Orange
    },
    {
        "quote": "Any fool can write code that a computer can understand. Good programmers write code that humans can understand.",
        "author": "Martin Fowler",
        "bio": "Software developer and author of 'Refactoring'",
        "wiki": "https://en.wikipedia.org/wiki/Martin_Fowler_(software_engineer)",
        "color": 0x1ABC9C  # Teal
    },
    {
        "quote": "First, solve the problem. Then, write the code.",
        "author": "John Johnson",
        "bio": "Software developer and problem solver",
        "wiki": None,
        "color": 0x95A5A6  # Gray
    },
    {
        "quote": "Code is like humor. When you have to explain it, it's bad.",
        "author": "Cory House",
        "bio": "Software architect and trainer",
        "wiki": None,
        "color": 0xE74C3C  # Red
    },
    {
        "quote": "The computer was born to solve problems that did not exist before.",
        "author": "Bill Gates",
        "bio": "Co-founder of Microsoft",
        "wiki": "https://en.wikipedia.org/wiki/Bill_Gates",
        "color": 0x00A4EF  # Microsoft blue
    },
    {
        "quote": "Measuring programming progress by lines of code is like measuring aircraft building progress by weight.",
        "author": "Bill Gates",
        "bio": "Co-founder of Microsoft",
        "wiki": "https://en.wikipedia.org/wiki/Bill_Gates",
        "color": 0x00A4EF
    },
    {
        "quote": "I'm not a great programmer; I'm just a good programmer with great habits.",
        "author": "Kent Beck",
        "bio": "Software engineer and creator of Extreme Programming",
        "wiki": "https://en.wikipedia.org/wiki/Kent_Beck",
        "color": 0x2ECC71  # Green
    },
    {
        "quote": "The only way to learn a new programming language is by writing programs in it.",
        "author": "Dennis Ritchie",
        "bio": "Creator of the C programming language and co-creator of Unix",
        "wiki": "https://en.wikipedia.org/wiki/Dennis_Ritchie",
        "color": 0x555555  # C gray
    },
    {
        "quote": "Simplicity is prerequisite for reliability.",
        "author": "Edsger Dijkstra",
        "bio": "Computer scientist and pioneer of structured programming",
        "wiki": "https://en.wikipedia.org/wiki/Edsger_W._Dijkstra",
        "color": 0x34495E  # Dark blue
    },
    {
        "quote": "Make it work, make it right, make it fast.",
        "author": "Kent Beck",
        "bio": "Software engineer and creator of Extreme Programming",
        "wiki": "https://en.wikipedia.org/wiki/Kent_Beck",
        "color": 0x2ECC71
    },
    {
        "quote": "If debugging is the process of removing software bugs, then programming must be the process of putting them in.",
        "author": "Edsger Dijkstra",
        "bio": "Computer scientist and pioneer of structured programming",
        "wiki": "https://en.wikipedia.org/wiki/Edsger_W._Dijkstra",
        "color": 0x34495E
    },
    {
        "quote": "There are only two hard things in Computer Science: cache invalidation and naming things.",
        "author": "Phil Karlton",
        "bio": "Computer scientist at Netscape",
        "wiki": None,
        "color": 0x16A085  # Dark teal
    },
    {
        "quote": "Software is a great combination between artistry and engineering.",
        "author": "Bill Gates",
        "bio": "Co-founder of Microsoft",
        "wiki": "https://en.wikipedia.org/wiki/Bill_Gates",
        "color": 0x00A4EF
    },
    {
        "quote": "The function of good software is to make the complex appear to be simple.",
        "author": "Grady Booch",
        "bio": "Software engineer and chief scientist at IBM",
        "wiki": "https://en.wikipedia.org/wiki/Grady_Booch",
        "color": 0x054ADA  # IBM blue
    },
    {
        "quote": "Every great developer you know got there by solving problems they were unqualified to solve until they actually did it.",
        "author": "Patrick McKenzie",
        "bio": "Software developer and entrepreneur",
        "wiki": None,
        "color": 0xF39C12  # Yellow
    },
    {
        "quote": "Walking on water and developing software from a specification are easy if both are frozen.",
        "author": "Edward V. Berard",
        "bio": "Software consultant and author",
        "wiki": None,
        "color": 0x3498DB
    },
    {
        "quote": "The best thing about a boolean is even if you are wrong, you are only off by a bit.",
        "author": "Anonymous",
        "bio": "Unknown coding humorist",
        "wiki": None,
        "color": 0x95A5A6
    },
    {
        "quote": "In theory, theory and practice are the same. In practice, they're not.",
        "author": "Yogi Berra",
        "bio": "Baseball player and philosopher (adapted for programming)",
        "wiki": "https://en.wikipedia.org/wiki/Yogi_Berra",
        "color": 0xE67E22
    },
    {
        "quote": "Perl – The only language that looks the same before and after RSA encryption.",
        "author": "Keith Bostic",
        "bio": "Software developer",
        "wiki": "https://en.wikipedia.org/wiki/Keith_Bostic",
        "color": 0x39457E  # Perl color
    },
    {
        "quote": "I'm not interested in computers. I'm interested in what they can do for people.",
        "author": "Steve Jobs",
        "bio": "Co-founder of Apple Inc.",
        "wiki": "https://en.wikipedia.org/wiki/Steve_Jobs",
        "color": 0x555555  # Apple gray
    },
    {
        "quote": "The most important property of a program is whether it accomplishes the intention of its user.",
        "author": "C.A.R. Hoare",
        "bio": "Computer scientist, Turing Award winner",
        "wiki": "https://en.wikipedia.org/wiki/Tony_Hoare",
        "color": 0x8E44AD
    },
    {
        "quote": "Software and cathedrals are much the same – first we build them, then we pray.",
        "author": "Sam Redwine",
        "bio": "Software engineer",
        "wiki": None,
        "color": 0x9B59B6
    },
    {
        "quote": "There are two ways to write error-free programs; only the third one works.",
        "author": "Alan J. Perlis",
        "bio": "First recipient of the Turing Award",
        "wiki": "https://en.wikipedia.org/wiki/Alan_Perlis",
        "color": 0xC0392B
    },
    {
        "quote": "Always code as if the guy who ends up maintaining your code will be a violent psychopath who knows where you live.",
        "author": "John Woods",
        "bio": "Software developer",
        "wiki": None,
        "color": 0xE74C3C
    },
    {
        "quote": "Programming is breaking of one big impossible task into several very small possible tasks.",
        "author": "Jazzwant",
        "bio": "Programming wisdom",
        "wiki": None,
        "color": 0x3498DB
    },
    {
        "quote": "Optimism is an occupational hazard of programming: feedback is the treatment.",
        "author": "Kent Beck",
        "bio": "Software engineer and creator of Extreme Programming",
        "wiki": "https://en.wikipedia.org/wiki/Kent_Beck",
        "color": 0x2ECC71
    },
    {
        "quote": "Before software can be reusable it first has to be usable.",
        "author": "Ralph Johnson",
        "bio": "Computer scientist, Gang of Four author",
        "wiki": "https://en.wikipedia.org/wiki/Ralph_Johnson_(computer_scientist)",
        "color": 0x16A085
    },
    {
        "quote": "The trouble with programmers is that you can never tell what a programmer is doing until it's too late.",
        "author": "Seymour Cray",
        "bio": "Supercomputer architect, founder of Cray Research",
        "wiki": "https://en.wikipedia.org/wiki/Seymour_Cray",
        "color": 0x34495E
    },
    {
        "quote": "Most good programmers do programming not because they expect to get paid or get adulation by the public, but because it is fun to program.",
        "author": "Linus Torvalds",
        "bio": "Creator of Linux and Git",
        "wiki": "https://en.wikipedia.org/wiki/Linus_Torvalds",
        "color": 0xFCC624
    },
    {
        "quote": "One of my most productive days was throwing away 1000 lines of code.",
        "author": "Ken Thompson",
        "bio": "Creator of Unix and Go programming language",
        "wiki": "https://en.wikipedia.org/wiki/Ken_Thompson",
        "color": 0x00ADD8  # Go blue
    },
    {
        "quote": "When in doubt, use brute force.",
        "author": "Ken Thompson",
        "bio": "Creator of Unix and Go programming language",
        "wiki": "https://en.wikipedia.org/wiki/Ken_Thompson",
        "color": 0x00ADD8
    },
    {
        "quote": "Deleted code is debugged code.",
        "author": "Jeff Sickel",
        "bio": "Software developer",
        "wiki": None,
        "color": 0x95A5A6
    },
    {
        "quote": "Debugging is twice as hard as writing the code in the first place. Therefore, if you write the code as cleverly as possible, you are, by definition, not smart enough to debug it.",
        "author": "Brian Kernighan",
        "bio": "Co-author of 'The C Programming Language'",
        "wiki": "https://en.wikipedia.org/wiki/Brian_Kernighan",
        "color": 0x555555
    },
    {
        "quote": "The best performance improvement is the transition from the nonworking state to the working state.",
        "author": "John Ousterhout",
        "bio": "Creator of Tcl programming language",
        "wiki": "https://en.wikipedia.org/wiki/John_Ousterhout",
        "color": 0xE67E22
    },
    {
        "quote": "The cheapest, fastest, and most reliable components are those that aren't there.",
        "author": "Gordon Bell",
        "bio": "Computer engineer, designed PDP computers",
        "wiki": "https://en.wikipedia.org/wiki/Gordon_Bell",
        "color": 0x2C3E50
    },
    {
        "quote": "It's not a bug – it's an undocumented feature.",
        "author": "Anonymous",
        "bio": "Every developer ever",
        "wiki": None,
        "color": 0xE74C3C
    },
    {
        "quote": "Without requirements or design, programming is the art of adding bugs to an empty text file.",
        "author": "Louis Srygley",
        "bio": "Software developer",
        "wiki": None,
        "color": 0xC0392B
    },
    {
        "quote": "Programs are meant to be read by humans and only incidentally for computers to execute.",
        "author": "Donald Knuth",
        "bio": "Father of algorithm analysis, creator of TeX",
        "wiki": "https://en.wikipedia.org/wiki/Donald_Knuth",
        "color": 0x8E44AD
    },
    {
        "quote": "Premature optimization is the root of all evil.",
        "author": "Donald Knuth",
        "bio": "Father of algorithm analysis, creator of TeX",
        "wiki": "https://en.wikipedia.org/wiki/Donald_Knuth",
        "color": 0x8E44AD
    },
    {
        "quote": "Computing is not about computers any more. It is about living.",
        "author": "Nicholas Negroponte",
        "bio": "Founder of MIT Media Lab",
        "wiki": "https://en.wikipedia.org/wiki/Nicholas_Negroponte",
        "color": 0xE74C3C
    },
    {
        "quote": "The value of a prototype is in the education it gives you, not in the code itself.",
        "author": "Alan Cooper",
        "bio": "Software designer, father of Visual Basic",
        "wiki": "https://en.wikipedia.org/wiki/Alan_Cooper",
        "color": 0x3498DB
    },
    {
        "quote": "Good code is its own best documentation.",
        "author": "Steve McConnell",
        "bio": "Author of 'Code Complete'",
        "wiki": "https://en.wikipedia.org/wiki/Steve_McConnell",
        "color": 0x27AE60
    },
    {
        "quote": "Testing leads to failure, and failure leads to understanding.",
        "author": "Burt Rutan",
        "bio": "Aerospace engineer",
        "wiki": "https://en.wikipedia.org/wiki/Burt_Rutan",
        "color": 0x2980B9
    },
    {
        "quote": "It works on my machine.",
        "author": "Anonymous",
        "bio": "Every developer debugging production issues",
        "wiki": None,
        "color": 0x95A5A6
    },
    {
        "quote": "Java is to JavaScript what car is to carpet.",
        "author": "Chris Heilmann",
        "bio": "Developer evangelist",
        "wiki": "https://en.wikipedia.org/wiki/Christian_Heilmann",
        "color": 0xF0DB4F  # JavaScript yellow
    },
    {
        "quote": "There are only two kinds of languages: the ones people complain about and the ones nobody uses.",
        "author": "Bjarne Stroustrup",
        "bio": "Creator of C++ programming language",
        "wiki": "https://en.wikipedia.org/wiki/Bjarne_Stroustrup",
        "color": 0x00599C  # C++ blue
    },
    {
        "quote": "C makes it easy to shoot yourself in the foot; C++ makes it harder, but when you do it blows your whole leg off.",
        "author": "Bjarne Stroustrup",
        "bio": "Creator of C++ programming language",
        "wiki": "https://en.wikipedia.org/wiki/Bjarne_Stroustrup",
        "color": 0x00599C
    },
    {
        "quote": "Python is executable pseudocode. Perl is executable line noise.",
        "author": "Bruce Eckel",
        "bio": "Author of 'Thinking in Java'",
        "wiki": "https://en.wikipedia.org/wiki/Bruce_Eckel",
        "color": 0x3776AB  # Python blue
    },
    {
        "quote": "If you think your users are idiots, only idiots will use it.",
        "author": "Linus Torvalds",
        "bio": "Creator of Linux and Git",
        "wiki": "https://en.wikipedia.org/wiki/Linus_Torvalds",
        "color": 0xFCC624
    },
    {
        "quote": "Should array indices start at 0 or 1? My compromise of 0.5 was rejected without, I thought, proper consideration.",
        "author": "Stan Kelly-Bootle",
        "bio": "Computer scientist and author",
        "wiki": "https://en.wikipedia.org/wiki/Stan_Kelly-Bootle",
        "color": 0xE67E22
    },
    {
        "quote": "Give someone a program, you frustrate them for a day; teach them how to program, you frustrate them for a lifetime.",
        "author": "David Leinweber",
        "bio": "Computational finance expert",
        "wiki": None,
        "color": 0xE74C3C
    },
    {
        "quote": "Real programmers don't comment their code. If it was hard to write, it should be hard to understand.",
        "author": "Anonymous",
        "bio": "Sarcastic programmer wisdom",
        "wiki": None,
        "color": 0x7F8C8D
    },
    {
        "quote": "The best thing about boolean is even if you are wrong, you are only off by a bit.",
        "author": "Anonymous",
        "bio": "Programming humor",
        "wiki": None,
        "color": 0x95A5A6
    },
    {
        "quote": "To err is human, but to really foul things up you need a computer.",
        "author": "Paul R. Ehrlich",
        "bio": "Biologist and author",
        "wiki": "https://en.wikipedia.org/wiki/Paul_R._Ehrlich",
        "color": 0xC0392B
    },
    {
        "quote": "A language that doesn't affect the way you think about programming is not worth knowing.",
        "author": "Alan J. Perlis",
        "bio": "First recipient of the Turing Award",
        "wiki": "https://en.wikipedia.org/wiki/Alan_Perlis",
        "color": 0xC0392B
    },
    {
        "quote": "The Internet? Is that thing still around?",
        "author": "Homer Simpson",
        "bio": "Animated character (often quoted by devs ironically)",
        "wiki": "https://en.wikipedia.org/wiki/Homer_Simpson",
        "color": 0xFFD700
    },
    {
        "quote": "Given enough eyeballs, all bugs are shallow.",
        "author": "Eric S. Raymond",
        "bio": "Open source advocate, author of 'The Cathedral and the Bazaar'",
        "wiki": "https://en.wikipedia.org/wiki/Eric_S._Raymond",
        "color": 0xD9534F
    },
    {
        "quote": "Smart data structures and dumb code works a lot better than the other way around.",
        "author": "Eric S. Raymond",
        "bio": "Open source advocate, author of 'The Cathedral and the Bazaar'",
        "wiki": "https://en.wikipedia.org/wiki/Eric_S._Raymond",
        "color": 0xD9534F
    },
    {
        "quote": "Every good work of software starts by scratching a developer's personal itch.",
        "author": "Eric S. Raymond",
        "bio": "Open source advocate, author of 'The Cathedral and the Bazaar'",
        "wiki": "https://en.wikipedia.org/wiki/Eric_S._Raymond",
        "color": 0xD9534F
    },
    {
        "quote": "Release early, release often.",
        "author": "Eric S. Raymond",
        "bio": "Open source advocate, author of 'The Cathedral and the Bazaar'",
        "wiki": "https://en.wikipedia.org/wiki/Eric_S._Raymond",
        "color": 0xD9534F
    },
    {
        "quote": "Software is like sex: it's better when it's free.",
        "author": "Linus Torvalds",
        "bio": "Creator of Linux and Git",
        "wiki": "https://en.wikipedia.org/wiki/Linus_Torvalds",
        "color": 0xFCC624
    },
    {
        "quote": "Microsoft isn't evil, they just make really crappy operating systems.",
        "author": "Linus Torvalds",
        "bio": "Creator of Linux and Git",
        "wiki": "https://en.wikipedia.org/wiki/Linus_Torvalds",
        "color": 0xFCC624
    },
    {
        "quote": "See, you not only have to be a good coder to create a system like Linux, you have to be a sneaky bastard too.",
        "author": "Linus Torvalds",
        "bio": "Creator of Linux and Git",
        "wiki": "https://en.wikipedia.org/wiki/Linus_Torvalds",
        "color": 0xFCC624
    },
    {
        "quote": "Intelligence is the ability to avoid doing work, yet getting the work done.",
        "author": "Linus Torvalds",
        "bio": "Creator of Linux and Git",
        "wiki": "https://en.wikipedia.org/wiki/Linus_Torvalds",
        "color": 0xFCC624
    },
    {
        "quote": "When you say 'I wrote a program that crashed Windows,' people just stare at you blankly and say 'Hey, I got those with the system, for free.'",
        "author": "Linus Torvalds",
        "bio": "Creator of Linux and Git",
        "wiki": "https://en.wikipedia.org/wiki/Linus_Torvalds",
        "color": 0xFCC624
    },
    {
        "quote": "Proprietary software is an injustice.",
        "author": "Richard Stallman",
        "bio": "Founder of GNU Project and Free Software Foundation",
        "wiki": "https://en.wikipedia.org/wiki/Richard_Stallman",
        "color": 0xA42E2B
    },
    {
        "quote": "If programmers deserve to be rewarded for creating innovative programs, by the same token they deserve to be punished if they restrict the use of these programs.",
        "author": "Richard Stallman",
        "bio": "Founder of GNU Project and Free Software Foundation",
        "wiki": "https://en.wikipedia.org/wiki/Richard_Stallman",
        "color": 0xA42E2B
    },
    {
        "quote": "Sharing is good, and with digital technology, sharing is easy.",
        "author": "Richard Stallman",
        "bio": "Founder of GNU Project and Free Software Foundation",
        "wiki": "https://en.wikipedia.org/wiki/Richard_Stallman",
        "color": 0xA42E2B
    },
    {
        "quote": "Free software is software that respects your freedom and the social solidarity of your community.",
        "author": "Richard Stallman",
        "bio": "Founder of GNU Project and Free Software Foundation",
        "wiki": "https://en.wikipedia.org/wiki/Richard_Stallman",
        "color": 0xA42E2B
    },
    {
        "quote": "I'd just like to interject for a moment. What you're referring to as Linux, is in fact, GNU/Linux.",
        "author": "Richard Stallman",
        "bio": "Founder of GNU Project and Free Software Foundation",
        "wiki": "https://en.wikipedia.org/wiki/Richard_Stallman",
        "color": 0xA42E2B
    },
    {
        "quote": "The Linux philosophy is 'Laugh in the face of danger.' Oops. Wrong One. 'Do it yourself.' Yes, that's it.",
        "author": "Linus Torvalds",
        "bio": "Creator of Linux and Git",
        "wiki": "https://en.wikipedia.org/wiki/Linus_Torvalds",
        "color": 0xFCC624
    },
    {
        "quote": "Open source is the only way to build software that will last.",
        "author": "Mitch Kapor",
        "bio": "Founder of Lotus Development Corporation",
        "wiki": "https://en.wikipedia.org/wiki/Mitch_Kapor",
        "color": 0x2980B9
    },
    {
        "quote": "The power of Open Source is the power of the people. The people rule.",
        "author": "Philippe Kahn",
        "bio": "Technology entrepreneur and innovator",
        "wiki": "https://en.wikipedia.org/wiki/Philippe_Kahn",
        "color": 0x27AE60
    },
    {
        "quote": "In open source, we feel strongly that to really do something well, you have to get a lot of people involved.",
        "author": "Linus Torvalds",
        "bio": "Creator of Linux and Git",
        "wiki": "https://en.wikipedia.org/wiki/Linus_Torvalds",
        "color": 0xFCC624
    },
    {
        "quote": "The great thing about mod_rewrite is it gives you all the configurability and flexibility of Sendmail. The downside to mod_rewrite is that it gives you all the configurability and flexibility of Sendmail.",
        "author": "Brian Behlendorf",
        "bio": "Co-founder of Apache HTTP Server",
        "wiki": "https://en.wikipedia.org/wiki/Brian_Behlendorf",
        "color": 0xD22128  # Apache red
    },
    {
        "quote": "The network is the computer.",
        "author": "John Gage",
        "bio": "Computer scientist at Sun Microsystems",
        "wiki": "https://en.wikipedia.org/wiki/John_Gage",
        "color": 0xFF8C00
    },
    {
        "quote": "Unix is simple. It just takes a genius to understand its simplicity.",
        "author": "Dennis Ritchie",
        "bio": "Creator of the C programming language and co-creator of Unix",
        "wiki": "https://en.wikipedia.org/wiki/Dennis_Ritchie",
        "color": 0x555555
    },
    {
        "quote": "The good thing about reinventing the wheel is that you can get a round one.",
        "author": "Douglas Crockford",
        "bio": "Developer of JSON and JavaScript architect",
        "wiki": "https://en.wikipedia.org/wiki/Douglas_Crockford",
        "color": 0xF0DB4F  # JavaScript yellow
    },
    {
        "quote": "Being open source meant that I could work on the technical side while others worked on documentation, marketing, and other things.",
        "author": "Rasmus Lerdorf",
        "bio": "Creator of PHP",
        "wiki": "https://en.wikipedia.org/wiki/Rasmus_Lerdorf",
        "color": 0x777BB3  # PHP purple
    },
    {
        "quote": "Linux is only free if your time has no value.",
        "author": "Jamie Zawinski",
        "bio": "Programmer, early Netscape contributor",
        "wiki": "https://en.wikipedia.org/wiki/Jamie_Zawinski",
        "color": 0x7F8C8D
    },
    {
        "quote": "Real programmers can write assembly code in any language.",
        "author": "Larry Wall",
        "bio": "Creator of Perl programming language",
        "wiki": "https://en.wikipedia.org/wiki/Larry_Wall",
        "color": 0x39457E
    },
    {
        "quote": "Most of you are familiar with the virtues of a programmer. There are three, of course: laziness, impatience, and hubris.",
        "author": "Larry Wall",
        "bio": "Creator of Perl programming language",
        "wiki": "https://en.wikipedia.org/wiki/Larry_Wall",
        "color": 0x39457E
    },
    {
        "quote": "We all agree on the necessity of compromise. We just can't agree on when it's necessary to compromise.",
        "author": "Larry Wall",
        "bio": "Creator of Perl programming language",
        "wiki": "https://en.wikipedia.org/wiki/Larry_Wall",
        "color": 0x39457E
    },
    {
        "quote": "The three chief virtues of a programmer are: Laziness, Impatience and Hubris.",
        "author": "Larry Wall",
        "bio": "Creator of Perl programming language",
        "wiki": "https://en.wikipedia.org/wiki/Larry_Wall",
        "color": 0x39457E
    },
    {
        "quote": "Unix was not designed to stop its users from doing stupid things, as that would also stop them from doing clever things.",
        "author": "Doug Gwyn",
        "bio": "Unix expert",
        "wiki": None,
        "color": 0x2C3E50
    },
    {
        "quote": "The best way to get a project done faster is to start sooner.",
        "author": "Jim Highsmith",
        "bio": "Software engineer and author",
        "wiki": "https://en.wikipedia.org/wiki/Jim_Highsmith",
        "color": 0x16A085
    },
    {
        "quote": "Beware of bugs in the above code; I have only proved it correct, not tried it.",
        "author": "Donald Knuth",
        "bio": "Father of algorithm analysis, creator of TeX",
        "wiki": "https://en.wikipedia.org/wiki/Donald_Knuth",
        "color": 0x8E44AD
    },
    {
        "quote": "If you're willing to restrict the flexibility of your approach, you can almost always do something better.",
        "author": "John Carmack",
        "bio": "Lead programmer of Doom, Quake, and VR pioneer",
        "wiki": "https://en.wikipedia.org/wiki/John_Carmack",
        "color": 0xC0392B
    },
    {
        "quote": "Low-level programming is good for the programmer's soul.",
        "author": "John Carmack",
        "bio": "Lead programmer of Doom, Quake, and VR pioneer",
        "wiki": "https://en.wikipedia.org/wiki/John_Carmack",
        "color": 0xC0392B
    },
    {
        "quote": "The best code is no code at all.",
        "author": "Jeff Atwood",
        "bio": "Co-founder of Stack Overflow",
        "wiki": "https://en.wikipedia.org/wiki/Jeff_Atwood",
        "color": 0xF48024  # Stack Overflow orange
    },
    {
        "quote": "If you can't explain it simply, you don't understand it well enough.",
        "author": "Albert Einstein",
        "bio": "Theoretical physicist (often applied to programming)",
        "wiki": "https://en.wikipedia.org/wiki/Albert_Einstein",
        "color": 0x34495E
    },
    {
        "quote": "We don't need to be perfect. We just need to be better than our competition.",
        "author": "Marc Andreessen",
        "bio": "Co-author of Mosaic, co-founder of Netscape",
        "wiki": "https://en.wikipedia.org/wiki/Marc_Andreessen",
        "color": 0x0E76A8
    },
    {
        "quote": "Software is eating the world.",
        "author": "Marc Andreessen",
        "bio": "Co-author of Mosaic, co-founder of Netscape",
        "wiki": "https://en.wikipedia.org/wiki/Marc_Andreessen",
        "color": 0x0E76A8
    },
    {
        "quote": "Move fast and break things.",
        "author": "Mark Zuckerberg",
        "bio": "Co-founder of Facebook/Meta",
        "wiki": "https://en.wikipedia.org/wiki/Mark_Zuckerberg",
        "color": 0x1877F2  # Facebook blue
    },
    {
        "quote": "Code never lies, comments sometimes do.",
        "author": "Ron Jeffries",
        "bio": "Co-founder of Extreme Programming",
        "wiki": "https://en.wikipedia.org/wiki/Ron_Jeffries",
        "color": 0x27AE60
    },
    {
        "quote": "The sooner you start to code, the longer the program will take.",
        "author": "Roy Carlson",
        "bio": "Software engineer",
        "wiki": None,
        "color": 0xE67E22
    },
    {
        "quote": "Hofstadter's Law: It always takes longer than you expect, even when you take into account Hofstadter's Law.",
        "author": "Douglas Hofstadter",
        "bio": "Cognitive scientist, author of 'Gödel, Escher, Bach'",
        "wiki": "https://en.wikipedia.org/wiki/Douglas_Hofstadter",
        "color": 0x9B59B6
    },
    {
        "quote": "A clever person solves a problem. A wise person avoids it.",
        "author": "Albert Einstein",
        "bio": "Theoretical physicist",
        "wiki": "https://en.wikipedia.org/wiki/Albert_Einstein",
        "color": 0x34495E
    },
    {
        "quote": "Programming today is a race between software engineers striving to build bigger and better idiot-proof programs, and the universe trying to produce bigger and better idiots. So far, the universe is winning.",
        "author": "Rick Cook",
        "bio": "Science fiction author",
        "wiki": "https://en.wikipedia.org/wiki/Rick_Cook",
        "color": 0xE74C3C
    },
    {
        "quote": "Good design adds value faster than it adds cost.",
        "author": "Thomas C. Gale",
        "bio": "Design executive",
        "wiki": None,
        "color": 0x3498DB
    },
    {
        "quote": "Simplicity is the soul of efficiency.",
        "author": "Austin Freeman",
        "bio": "British writer",
        "wiki": "https://en.wikipedia.org/wiki/R._Austin_Freeman",
        "color": 0x1ABC9C
    },
    {
        "quote": "Documentation is a love letter that you write to your future self.",
        "author": "Damian Conway",
        "bio": "Computer scientist and Perl developer",
        "wiki": "https://en.wikipedia.org/wiki/Damian_Conway",
        "color": 0x39457E
    },
    {
        "quote": "There are two ways of constructing a software design: One way is to make it so simple that there are obviously no deficiencies, and the other way is to make it so complicated that there are no obvious deficiencies.",
        "author": "C.A.R. Hoare",
        "bio": "Computer scientist, Turing Award winner",
        "wiki": "https://en.wikipedia.org/wiki/Tony_Hoare",
        "color": 0x8E44AD
    },
    {
        "quote": "The only truly secure system is one that is powered off, cast in a block of concrete and sealed in a lead-lined room with armed guards.",
        "author": "Gene Spafford",
        "bio": "Computer security expert",
        "wiki": "https://en.wikipedia.org/wiki/Gene_Spafford",
        "color": 0xC0392B
    },
    {
        "quote": "In God we trust. All others must bring data.",
        "author": "W. Edwards Deming",
        "bio": "Engineer and management consultant",
        "wiki": "https://en.wikipedia.org/wiki/W._Edwards_Deming",
        "color": 0x2C3E50
    },
    {
        "quote": "Weeks of coding can save you hours of planning.",
        "author": "Anonymous",
        "bio": "Programming wisdom",
        "wiki": None,
        "color": 0xE74C3C
    },
    {
        "quote": "In software, we rarely have meaningful requirements. Even if we do, the only measure of success that matters is whether our solution solves the customer's shifting idea of what their problem is.",
        "author": "Jeff Atwood",
        "bio": "Co-founder of Stack Overflow",
        "wiki": "https://en.wikipedia.org/wiki/Jeff_Atwood",
        "color": 0xF48024
    },
    {
        "quote": "Computer science education cannot make anybody an expert programmer any more than studying brushes and pigment can make somebody an expert painter.",
        "author": "Eric S. Raymond",
        "bio": "Open source advocate, author of 'The Cathedral and the Bazaar'",
        "wiki": "https://en.wikipedia.org/wiki/Eric_S._Raymond",
        "color": 0xD9534F
    },
    {
        "quote": "The purpose of software engineering is to control complexity, not to create it.",
        "author": "Pamela Zave",
        "bio": "Computer scientist at AT&T Labs",
        "wiki": "https://en.wikipedia.org/wiki/Pamela_Zave",
        "color": 0x3498DB
    },
    {
        "quote": "Don't worry if it doesn't work right. If everything did, you'd be out of a job.",
        "author": "Mosher's Law of Software Engineering",
        "bio": "Software engineering wisdom",
        "wiki": None,
        "color": 0x95A5A6
    },
    {
        "quote": "It's not a bug, it's a feature.",
        "author": "Anonymous",
        "bio": "Every developer's defense mechanism",
        "wiki": None,
        "color": 0xF39C12
    },
    {
        "quote": "I have always wished for my computer to be as easy to use as my telephone; my wish has come true because I can no longer figure out how to use my telephone.",
        "author": "Bjarne Stroustrup",
        "bio": "Creator of C++ programming language",
        "wiki": "https://en.wikipedia.org/wiki/Bjarne_Stroustrup",
        "color": 0x00599C
    },
    {
        "quote": "Software undergoes beta testing shortly before it's released. Beta is Latin for 'still doesn't work.'",
        "author": "Anonymous",
        "bio": "Tech industry humor",
        "wiki": None,
        "color": 0xE67E22
    },
    {
        "quote": "The bearing of a child takes nine months, no matter how many women are assigned.",
        "author": "Frederick P. Brooks Jr.",
        "bio": "Computer scientist, author of 'The Mythical Man-Month'",
        "wiki": "https://en.wikipedia.org/wiki/Fred_Brooks",
        "color": 0x34495E
    },
    {
        "quote": "Adding manpower to a late software project makes it later.",
        "author": "Frederick P. Brooks Jr.",
        "bio": "Computer scientist, author of 'The Mythical Man-Month'",
        "wiki": "https://en.wikipedia.org/wiki/Fred_Brooks",
        "color": 0x34495E
    },
    {
        "quote": "How does a project get to be a year behind schedule? One day at a time.",
        "author": "Frederick P. Brooks Jr.",
        "bio": "Computer scientist, author of 'The Mythical Man-Month'",
        "wiki": "https://en.wikipedia.org/wiki/Fred_Brooks",
        "color": 0x34495E
    },
    {
        "quote": "Plan to throw one away; you will, anyhow.",
        "author": "Frederick P. Brooks Jr.",
        "bio": "Computer scientist, author of 'The Mythical Man-Month'",
        "wiki": "https://en.wikipedia.org/wiki/Fred_Brooks",
        "color": 0x34495E
    },
    {
        "quote": "You can't have great software without a great team, and most software teams behave like dysfunctional families.",
        "author": "Jim McCarthy",
        "bio": "Software development author",
        "wiki": None,
        "color": 0xE74C3C
    },
    {
        "quote": "If at first you don't succeed, call it version 1.0.",
        "author": "Anonymous",
        "bio": "Software versioning humor",
        "wiki": None,
        "color": 0x95A5A6
    },
    {
        "quote": "There's nothing more permanent than a temporary hack.",
        "author": "Kyle Simpson",
        "bio": "JavaScript developer and author",
        "wiki": None,
        "color": 0xF0DB4F
    },
    {
        "quote": "Legacy code is code without tests.",
        "author": "Michael Feathers",
        "bio": "Author of 'Working Effectively with Legacy Code'",
        "wiki": "https://en.wikipedia.org/wiki/Michael_Feathers",
        "color": 0xC0392B
    },
    {
        "quote": "The most disastrous thing that you can ever learn is your first programming language.",
        "author": "Alan Kay",
        "bio": "Computer scientist and pioneer of object-oriented programming",
        "wiki": "https://en.wikipedia.org/wiki/Alan_Kay",
        "color": 0xE67E22
    },
    {
        "quote": "Don't comment bad code—rewrite it.",
        "author": "Brian W. Kernighan",
        "bio": "Co-author of 'The C Programming Language'",
        "wiki": "https://en.wikipedia.org/wiki/Brian_Kernighan",
        "color": 0x555555
    },
    {
        "quote": "Controlling complexity is the essence of computer programming.",
        "author": "Brian W. Kernighan",
        "bio": "Co-author of 'The C Programming Language'",
        "wiki": "https://en.wikipedia.org/wiki/Brian_Kernighan",
        "color": 0x555555
    },
    {
        "quote": "Everyone knows that debugging is twice as hard as writing a program in the first place. So if you're as clever as you can be when you write it, how will you ever debug it?",
        "author": "Brian W. Kernighan",
        "bio": "Co-author of 'The C Programming Language'",
        "wiki": "https://en.wikipedia.org/wiki/Brian_Kernighan",
        "color": 0x555555
    },
    {
        "quote": "It's harder to read code than to write it.",
        "author": "Joel Spolsky",
        "bio": "Co-founder of Stack Overflow and Trello",
        "wiki": "https://en.wikipedia.org/wiki/Joel_Spolsky",
        "color": 0xF48024
    },
    {
        "quote": "Good code is its own best documentation.",
        "author": "Steve McConnell",
        "bio": "Author of 'Code Complete'",
        "wiki": "https://en.wikipedia.org/wiki/Steve_McConnell",
        "color": 0x27AE60
    },
    {
        "quote": "Technology is anything that wasn't around when you were born.",
        "author": "Alan Kay",
        "bio": "Computer scientist and pioneer of object-oriented programming",
        "wiki": "https://en.wikipedia.org/wiki/Alan_Kay",
        "color": 0xE67E22
    },
    {
        "quote": "The best error message is the one that never shows up.",
        "author": "Thomas Fuchs",
        "bio": "JavaScript developer",
        "wiki": None,
        "color": 0x2ECC71
    },
    {
        "quote": "Simplicity is hard to build, easy to use, and hard to charge for. Complexity is easy to build, hard to use, and easy to charge for.",
        "author": "Chris Sacca",
        "bio": "Venture capitalist and entrepreneur",
        "wiki": "https://en.wikipedia.org/wiki/Chris_Sacca",
        "color": 0x1ABC9C
    },
    {
        "quote": "It's not at all important to get it right the first time. It's vitally important to get it right the last time.",
        "author": "Andrew Hunt",
        "bio": "Co-author of 'The Pragmatic Programmer'",
        "wiki": "https://en.wikipedia.org/wiki/Andy_Hunt_(author)",
        "color": 0x16A085
    },
    {
        "quote": "No amount of testing can prove a software right, a single test can prove a software wrong.",
        "author": "Amir Ghahrai",
        "bio": "Test automation expert",
        "wiki": None,
        "color": 0xE74C3C
    },
    {
        "quote": "There are 10 types of people in the world: those who understand binary, and those who don't.",
        "author": "Anonymous",
        "bio": "Classic programmer joke",
        "wiki": None,
        "color": 0x95A5A6
    },
    {
        "quote": "99 little bugs in the code, 99 little bugs. Take one down, patch it around, 127 little bugs in the code.",
        "author": "Anonymous",
        "bio": "Programming reality",
        "wiki": None,
        "color": 0xE74C3C
    },
    {
        "quote": "A SQL query walks into a bar, walks up to two tables and asks, 'Can I join you?'",
        "author": "Anonymous",
        "bio": "Database humor",
        "wiki": None,
        "color": 0xF29111
    },
    {
        "quote": "Programming is like sex: one mistake and you have to support it for the rest of your life.",
        "author": "Michael Sinz",
        "bio": "Software developer",
        "wiki": None,
        "color": 0xC0392B
    },
    {
        "quote": "A programmer is someone who solves a problem you didn't know you had in a way you don't understand.",
        "author": "Anonymous",
        "bio": "Tech industry observation",
        "wiki": None,
        "color": 0x9B59B6
    },
    {
        "quote": "If debugging is the process of removing bugs, then programming must be the process of putting them in.",
        "author": "Edsger Dijkstra",
        "bio": "Computer scientist and pioneer of structured programming",
        "wiki": "https://en.wikipedia.org/wiki/Edsger_W._Dijkstra",
        "color": 0x34495E
    },
    {
        "quote": "Computer Science is no more about computers than astronomy is about telescopes.",
        "author": "Edsger Dijkstra",
        "bio": "Computer scientist and pioneer of structured programming",
        "wiki": "https://en.wikipedia.org/wiki/Edsger_W._Dijkstra",
        "color": 0x34495E
    },
    {
        "quote": "The question of whether a computer can think is no more interesting than the question of whether a submarine can swim.",
        "author": "Edsger Dijkstra",
        "bio": "Computer scientist and pioneer of structured programming",
        "wiki": "https://en.wikipedia.org/wiki/Edsger_W._Dijkstra",
        "color": 0x34495E
    },
    {
        "quote": "Testing can show the presence of bugs but never their absence.",
        "author": "Edsger Dijkstra",
        "bio": "Computer scientist and pioneer of structured programming",
        "wiki": "https://en.wikipedia.org/wiki/Edsger_W._Dijkstra",
        "color": 0x34495E
    },
    {
        "quote": "Simplicity is the ultimate sophistication.",
        "author": "Leonardo da Vinci",
        "bio": "Renaissance polymath (often applied to software design)",
        "wiki": "https://en.wikipedia.org/wiki/Leonardo_da_Vinci",
        "color": 0x8B4513
    },
    {
        "quote": "Make everything as simple as possible, but not simpler.",
        "author": "Albert Einstein",
        "bio": "Theoretical physicist",
        "wiki": "https://en.wikipedia.org/wiki/Albert_Einstein",
        "color": 0x34495E
    },
    {
        "quote": "The best way to predict the future is to implement it.",
        "author": "David Heinemeier Hansson",
        "bio": "Creator of Ruby on Rails",
        "wiki": "https://en.wikipedia.org/wiki/David_Heinemeier_Hansson",
        "color": 0xCC0000  # Ruby red
    },
    {
        "quote": "Convention over configuration.",
        "author": "David Heinemeier Hansson",
        "bio": "Creator of Ruby on Rails",
        "wiki": "https://en.wikipedia.org/wiki/David_Heinemeier_Hansson",
        "color": 0xCC0000
    },
    {
        "quote": "Optimize for programmer happiness.",
        "author": "Yukihiro Matsumoto",
        "bio": "Creator of Ruby programming language",
        "wiki": "https://en.wikipedia.org/wiki/Yukihiro_Matsumoto",
        "color": 0xCC342D  # Ruby red
    },
    {
        "quote": "Ruby is designed to make programmers happy.",
        "author": "Yukihiro Matsumoto",
        "bio": "Creator of Ruby programming language",
        "wiki": "https://en.wikipedia.org/wiki/Yukihiro_Matsumoto",
        "color": 0xCC342D
    },
    {
        "quote": "Beautiful is better than ugly. Explicit is better than implicit. Simple is better than complex.",
        "author": "Tim Peters",
        "bio": "Python core developer, author of 'The Zen of Python'",
        "wiki": "https://en.wikipedia.org/wiki/Tim_Peters_(software_engineer)",
        "color": 0x3776AB  # Python blue
    },
    {
        "quote": "Readability counts.",
        "author": "Tim Peters",
        "bio": "Python core developer, author of 'The Zen of Python'",
        "wiki": "https://en.wikipedia.org/wiki/Tim_Peters_(software_engineer)",
        "color": 0x3776AB
    },
    {
        "quote": "There should be one-- and preferably only one --obvious way to do it.",
        "author": "Tim Peters",
        "bio": "Python core developer, author of 'The Zen of Python'",
        "wiki": "https://en.wikipedia.org/wiki/Tim_Peters_(software_engineer)",
        "color": 0x3776AB
    },
    {
        "quote": "Namespaces are one honking great idea -- let's do more of those!",
        "author": "Tim Peters",
        "bio": "Python core developer, author of 'The Zen of Python'",
        "wiki": "https://en.wikipedia.org/wiki/Tim_Peters_(software_engineer)",
        "color": 0x3776AB
    },
    {
        "quote": "Errors should never pass silently. Unless explicitly silenced.",
        "author": "Tim Peters",
        "bio": "Python core developer, author of 'The Zen of Python'",
        "wiki": "https://en.wikipedia.org/wiki/Tim_Peters_(software_engineer)",
        "color": 0x3776AB
    },
    {
        "quote": "Now is better than never. Although never is often better than *right* now.",
        "author": "Tim Peters",
        "bio": "Python core developer, author of 'The Zen of Python'",
        "wiki": "https://en.wikipedia.org/wiki/Tim_Peters_(software_engineer)",
        "color": 0x3776AB
    },
    {
        "quote": "The art of programming is the art of organizing complexity.",
        "author": "Edsger Dijkstra",
        "bio": "Computer scientist and pioneer of structured programming",
        "wiki": "https://en.wikipedia.org/wiki/Edsger_W._Dijkstra",
        "color": 0x34495E
    },
    {
        "quote": "Hofstadter's Law will apply to your project whether you expect it to or not.",
        "author": "Douglas Hofstadter",
        "bio": "Cognitive scientist, author of 'Gödel, Escher, Bach'",
        "wiki": "https://en.wikipedia.org/wiki/Douglas_Hofstadter",
        "color": 0x9B59B6
    },
    {
        "quote": "Before software should be reusable, it should be usable.",
        "author": "Ralph Johnson",
        "bio": "Computer scientist, Gang of Four author",
        "wiki": "https://en.wikipedia.org/wiki/Ralph_Johnson_(computer_scientist)",
        "color": 0x16A085
    },
    {
        "quote": "Code reuse is the Holy Grail of Software Engineering.",
        "author": "Douglas Crockford",
        "bio": "Developer of JSON and JavaScript architect",
        "wiki": "https://en.wikipedia.org/wiki/Douglas_Crockford",
        "color": 0xF0DB4F
    },
    {
        "quote": "JavaScript is the duct tape of the Internet.",
        "author": "Charlie Campbell",
        "bio": "Web developer",
        "wiki": None,
        "color": 0xF0DB4F
    },
    {
        "quote": "Any application that can be written in JavaScript, will eventually be written in JavaScript.",
        "author": "Jeff Atwood",
        "bio": "Co-founder of Stack Overflow (Atwood's Law)",
        "wiki": "https://en.wikipedia.org/wiki/Jeff_Atwood",
        "color": 0xF48024
    },
    {
        "quote": "Java is to JavaScript as ham is to hamster.",
        "author": "Jeremy Keith",
        "bio": "Web developer and author",
        "wiki": "https://en.wikipedia.org/wiki/Jeremy_Keith",
        "color": 0xF0DB4F
    },
    {
        "quote": "The only way to go fast is to go well.",
        "author": "Robert C. Martin",
        "bio": "Software engineer, author of 'Clean Code'",
        "wiki": "https://en.wikipedia.org/wiki/Robert_C._Martin",
        "color": 0x2ECC71
    },
    {
        "quote": "Clean code always looks like it was written by someone who cares.",
        "author": "Robert C. Martin",
        "bio": "Software engineer, author of 'Clean Code'",
        "wiki": "https://en.wikipedia.org/wiki/Robert_C._Martin",
        "color": 0x2ECC71
    },
    {
        "quote": "Truth can only be found in one place: the code.",
        "author": "Robert C. Martin",
        "bio": "Software engineer, author of 'Clean Code'",
        "wiki": "https://en.wikipedia.org/wiki/Robert_C._Martin",
        "color": 0x2ECC71
    },
    {
        "quote": "You should name a variable using the same care with which you name a first-born child.",
        "author": "Robert C. Martin",
        "bio": "Software engineer, author of 'Clean Code'",
        "wiki": "https://en.wikipedia.org/wiki/Robert_C._Martin",
        "color": 0x2ECC71
    },
    {
        "quote": "Indeed, the ratio of time spent reading versus writing is well over 10 to 1. We are constantly reading old code as part of the effort to write new code.",
        "author": "Robert C. Martin",
        "bio": "Software engineer, author of 'Clean Code'",
        "wiki": "https://en.wikipedia.org/wiki/Robert_C._Martin",
        "color": 0x2ECC71
    },
    {
        "quote": "So if you want to go fast, if you want to get done quickly, if you want your code to be easy to write, make it easy to read.",
        "author": "Robert C. Martin",
        "bio": "Software engineer, author of 'Clean Code'",
        "wiki": "https://en.wikipedia.org/wiki/Robert_C._Martin",
        "color": 0x2ECC71
    },
    {
        "quote": "Functions should do one thing. They should do it well. They should do it only.",
        "author": "Robert C. Martin",
        "bio": "Software engineer, author of 'Clean Code'",
        "wiki": "https://en.wikipedia.org/wiki/Robert_C._Martin",
        "color": 0x2ECC71
    },
    {
        "quote": "Don't Repeat Yourself (DRY).",
        "author": "Andy Hunt",
        "bio": "Co-author of 'The Pragmatic Programmer'",
        "wiki": "https://en.wikipedia.org/wiki/Andy_Hunt_(author)",
        "color": 0x16A085
    },
    {
        "quote": "YAGNI: You Aren't Gonna Need It.",
        "author": "Ron Jeffries",
        "bio": "Co-founder of Extreme Programming",
        "wiki": "https://en.wikipedia.org/wiki/Ron_Jeffries",
        "color": 0x27AE60
    },
    {
        "quote": "Keep It Simple, Stupid (KISS).",
        "author": "Kelly Johnson",
        "bio": "Lead engineer at Lockheed Skunk Works",
        "wiki": "https://en.wikipedia.org/wiki/Kelly_Johnson_(engineer)",
        "color": 0x3498DB
    },
    {
        "quote": "Perfection is achieved not when there is nothing more to add, but when there is nothing left to take away.",
        "author": "Antoine de Saint-Exupéry",
        "bio": "Author (often applied to software design)",
        "wiki": "https://en.wikipedia.org/wiki/Antoine_de_Saint-Exup%C3%A9ry",
        "color": 0x9B59B6
    },
    {
        "quote": "The road to hell is paved with good intentions.",
        "author": "Anonymous",
        "bio": "Applied to tech debt and shortcuts",
        "wiki": None,
        "color": 0xC0392B
    },
    {
        "quote": "Measuring programming progress by lines of code is like measuring aircraft building progress by weight.",
        "author": "Bill Gates",
        "bio": "Co-founder of Microsoft",
        "wiki": "https://en.wikipedia.org/wiki/Bill_Gates",
        "color": 0x00A4EF
    },
    {
        "quote": "It's fine to celebrate success, but it is more important to heed the lessons of failure.",
        "author": "Bill Gates",
        "bio": "Co-founder of Microsoft",
        "wiki": "https://en.wikipedia.org/wiki/Bill_Gates",
        "color": 0x00A4EF
    },
    {
        "quote": "Your most unhappy customers are your greatest source of learning.",
        "author": "Bill Gates",
        "bio": "Co-founder of Microsoft",
        "wiki": "https://en.wikipedia.org/wiki/Bill_Gates",
        "color": 0x00A4EF
    },
    {
        "quote": "Success is a lousy teacher. It seduces smart people into thinking they can't lose.",
        "author": "Bill Gates",
        "bio": "Co-founder of Microsoft",
        "wiki": "https://en.wikipedia.org/wiki/Bill_Gates",
        "color": 0x00A4EF
    },
    {
        "quote": "The advance of technology is based on making it fit in so that you don't really even notice it, so it's part of everyday life.",
        "author": "Bill Gates",
        "bio": "Co-founder of Microsoft",
        "wiki": "https://en.wikipedia.org/wiki/Bill_Gates",
        "color": 0x00A4EF
    },
    {
        "quote": "Innovation is saying no to 1,000 things.",
        "author": "Steve Jobs",
        "bio": "Co-founder of Apple Inc.",
        "wiki": "https://en.wikipedia.org/wiki/Steve_Jobs",
        "color": 0x555555
    },
    {
        "quote": "Design is not just what it looks like and feels like. Design is how it works.",
        "author": "Steve Jobs",
        "bio": "Co-founder of Apple Inc.",
        "wiki": "https://en.wikipedia.org/wiki/Steve_Jobs",
        "color": 0x555555
    },
    {
        "quote": "Simple can be harder than complex: You have to work hard to get your thinking clean to make it simple.",
        "author": "Steve Jobs",
        "bio": "Co-founder of Apple Inc.",
        "wiki": "https://en.wikipedia.org/wiki/Steve_Jobs",
        "color": 0x555555
    },
    {
        "quote": "Quality is more important than quantity. One home run is much better than two doubles.",
        "author": "Steve Jobs",
        "bio": "Co-founder of Apple Inc.",
        "wiki": "https://en.wikipedia.org/wiki/Steve_Jobs",
        "color": 0x555555
    },
    {
        "quote": "Stay hungry, stay foolish.",
        "author": "Steve Jobs",
        "bio": "Co-founder of Apple Inc.",
        "wiki": "https://en.wikipedia.org/wiki/Steve_Jobs",
        "color": 0x555555
    },
    {
        "quote": "Real artists ship.",
        "author": "Steve Jobs",
        "bio": "Co-founder of Apple Inc.",
        "wiki": "https://en.wikipedia.org/wiki/Steve_Jobs",
        "color": 0x555555
    },
    {
        "quote": "Most good programmers do programming not because they expect to get paid or get adulation by the public, but because it is fun to program.",
        "author": "Linus Torvalds",
        "bio": "Creator of Linux and Git",
        "wiki": "https://en.wikipedia.org/wiki/Linus_Torvalds",
        "color": 0xFCC624
    },
    {
        "quote": "Intelligence is the ability to avoid doing work, yet getting the work done.",
        "author": "Linus Torvalds",
        "bio": "Creator of Linux and Git",
        "wiki": "https://en.wikipedia.org/wiki/Linus_Torvalds",
        "color": 0xFCC624
    },
    {
        "quote": "Software is like sex: it's better when it's free.",
        "author": "Linus Torvalds",
        "bio": "Creator of Linux and Git",
        "wiki": "https://en.wikipedia.org/wiki/Linus_Torvalds",
        "color": 0xFCC624
    },
    {
        "quote": "Theory and practice sometimes clash. And when that happens, theory loses. Every single time.",
        "author": "Linus Torvalds",
        "bio": "Creator of Linux and Git",
        "wiki": "https://en.wikipedia.org/wiki/Linus_Torvalds",
        "color": 0xFCC624
    },
    {
        "quote": "A computer lets you make more mistakes faster than any invention in human history - with the possible exceptions of handguns and tequila.",
        "author": "Mitch Radcliffe",
        "bio": "Technology writer",
        "wiki": None,
        "color": 0xE67E22
    },
    {
        "quote": "That's the thing about people who think they hate computers. What they really hate is lousy programmers.",
        "author": "Larry Niven",
        "bio": "Science fiction author",
        "wiki": "https://en.wikipedia.org/wiki/Larry_Niven",
        "color": 0x9B59B6
    },
    {
        "quote": "The Internet? Is that thing still around?",
        "author": "Homer Simpson",
        "bio": "Fictional character (tech humor)",
        "wiki": None,
        "color": 0xFFA500
    },
    {
        "quote": "The Web as I envisaged it, we have not seen it yet. The future is still so much bigger than the past.",
        "author": "Tim Berners-Lee",
        "bio": "Inventor of the World Wide Web",
        "wiki": "https://en.wikipedia.org/wiki/Tim_Berners-Lee",
        "color": 0x005A9C
    },
    {
        "quote": "The original idea of the web was that it should be a collaborative space where you can communicate through sharing information.",
        "author": "Tim Berners-Lee",
        "bio": "Inventor of the World Wide Web",
        "wiki": "https://en.wikipedia.org/wiki/Tim_Berners-Lee",
        "color": 0x005A9C
    },
    {
        "quote": "The web is more a social creation than a technical one. I designed it for a social effect.",
        "author": "Tim Berners-Lee",
        "bio": "Inventor of the World Wide Web",
        "wiki": "https://en.wikipedia.org/wiki/Tim_Berners-Lee",
        "color": 0x005A9C
    },
    {
        "quote": "We can only see a short distance ahead, but we can see plenty there that needs to be done.",
        "author": "Alan Turing",
        "bio": "Father of computer science and artificial intelligence",
        "wiki": "https://en.wikipedia.org/wiki/Alan_Turing",
        "color": 0x34495E
    },
    {
        "quote": "Sometimes it is the people no one can imagine anything of who do the things no one can imagine.",
        "author": "Alan Turing",
        "bio": "Father of computer science and artificial intelligence",
        "wiki": "https://en.wikipedia.org/wiki/Alan_Turing",
        "color": 0x34495E
    },
    {
        "quote": "A computer would deserve to be called intelligent if it could deceive a human into believing that it was human.",
        "author": "Alan Turing",
        "bio": "Father of computer science and artificial intelligence",
        "wiki": "https://en.wikipedia.org/wiki/Alan_Turing",
        "color": 0x34495E
    },
    {
        "quote": "We are not interested in the fact that the brain has the consistency of cold porridge.",
        "author": "Alan Turing",
        "bio": "Father of computer science and artificial intelligence",
        "wiki": "https://en.wikipedia.org/wiki/Alan_Turing",
        "color": 0x34495E
    },
    {
        "quote": "The Analytical Engine has no pretensions whatever to originate anything. It can do whatever we know how to order it to perform.",
        "author": "Ada Lovelace",
        "bio": "First computer programmer, mathematician",
        "wiki": "https://en.wikipedia.org/wiki/Ada_Lovelace",
        "color": 0x9C27B0
    },
    {
        "quote": "That brain of mine is something more than merely mortal; as time will show.",
        "author": "Ada Lovelace",
        "bio": "First computer programmer, mathematician",
        "wiki": "https://en.wikipedia.org/wiki/Ada_Lovelace",
        "color": 0x9C27B0
    },
    {
        "quote": "I never am really satisfied that I understand anything; because, understand it well as I may, my comprehension can only be an infinitesimal fraction of all I want to understand.",
        "author": "Ada Lovelace",
        "bio": "First computer programmer, mathematician",
        "wiki": "https://en.wikipedia.org/wiki/Ada_Lovelace",
        "color": 0x9C27B0
    },
    {
        "quote": "If you optimize everything, you will always be unhappy.",
        "author": "Donald Knuth",
        "bio": "Author of 'The Art of Computer Programming'",
        "wiki": "https://en.wikipedia.org/wiki/Donald_Knuth",
        "color": 0x8B4513
    },
    {
        "quote": "Science is what we understand well enough to explain to a computer. Art is everything else we do.",
        "author": "Donald Knuth",
        "bio": "Author of 'The Art of Computer Programming'",
        "wiki": "https://en.wikipedia.org/wiki/Donald_Knuth",
        "color": 0x8B4513
    },
    {
        "quote": "An algorithm must be seen to be believed.",
        "author": "Donald Knuth",
        "bio": "Author of 'The Art of Computer Programming'",
        "wiki": "https://en.wikipedia.org/wiki/Donald_Knuth",
        "color": 0x8B4513
    },
    {
        "quote": "Let us change our traditional attitude to the construction of programs: Instead of imagining that our main task is to instruct a computer what to do, let us concentrate rather on explaining to human beings what we want a computer to do.",
        "author": "Donald Knuth",
        "bio": "Author of 'The Art of Computer Programming'",
        "wiki": "https://en.wikipedia.org/wiki/Donald_Knuth",
        "color": 0x8B4513
    },
    {
        "quote": "Beware of bugs in the above code; I have only proved it correct, not tried it.",
        "author": "Donald Knuth",
        "bio": "Author of 'The Art of Computer Programming'",
        "wiki": "https://en.wikipedia.org/wiki/Donald_Knuth",
        "color": 0x8B4513
    },
    {
        "quote": "The real problem is that programmers have spent far too much time worrying about efficiency in the wrong places and at the wrong times.",
        "author": "Donald Knuth",
        "bio": "Author of 'The Art of Computer Programming'",
        "wiki": "https://en.wikipedia.org/wiki/Donald_Knuth",
        "color": 0x8B4513
    },
    {
        "quote": "Email is a wonderful thing for people whose role in life is to be on top of things. But not for me; my role is to be on the bottom of things.",
        "author": "Donald Knuth",
        "bio": "Author of 'The Art of Computer Programming'",
        "wiki": "https://en.wikipedia.org/wiki/Donald_Knuth",
        "color": 0x8B4513
    },
    {
        "quote": "Programming is the art of telling another human what one wants the computer to do.",
        "author": "Donald Knuth",
        "bio": "Author of 'The Art of Computer Programming'",
        "wiki": "https://en.wikipedia.org/wiki/Donald_Knuth",
        "color": 0x8B4513
    },
    {
        "quote": "The best programs are written so that computing machines can perform them quickly and so that human beings can understand them clearly.",
        "author": "Donald Knuth",
        "bio": "Author of 'The Art of Computer Programming'",
        "wiki": "https://en.wikipedia.org/wiki/Donald_Knuth",
        "color": 0x8B4513
    },
    {
        "quote": "I think Microsoft named .Net so it wouldn't show up in a Unix directory listing.",
        "author": "Oktal",
        "bio": "Developer community humor",
        "wiki": None,
        "color": 0xE74C3C
    },
    {
        "quote": "Windows NT: Nice Try.",
        "author": "Anonymous",
        "bio": "Tech industry humor",
        "wiki": None,
        "color": 0x95A5A6
    },
    {
        "quote": "Unix is user-friendly. It's just very selective about who its friends are.",
        "author": "Anonymous",
        "bio": "Unix community humor",
        "wiki": None,
        "color": 0x34495E
    },
    {
        "quote": "My software never has bugs. It just develops random features.",
        "author": "Anonymous",
        "bio": "Developer humor",
        "wiki": None,
        "color": 0xE67E22
    },
    {
        "quote": "I would love to change the world, but they won't give me the source code.",
        "author": "Anonymous",
        "bio": "Developer humor",
        "wiki": None,
        "color": 0x3498DB
    },
    {
        "quote": "There are two ways to write error-free programs; only the third one works.",
        "author": "Alan J. Perlis",
        "bio": "First recipient of the Turing Award",
        "wiki": "https://en.wikipedia.org/wiki/Alan_Perlis",
        "color": 0x16A085
    },
    {
        "quote": "A language that doesn't affect the way you think about programming is not worth knowing.",
        "author": "Alan J. Perlis",
        "bio": "First recipient of the Turing Award",
        "wiki": "https://en.wikipedia.org/wiki/Alan_Perlis",
        "color": 0x16A085
    },
    {
        "quote": "Fools ignore complexity. Pragmatists suffer it. Some can avoid it. Geniuses remove it.",
        "author": "Alan J. Perlis",
        "bio": "First recipient of the Turing Award",
        "wiki": "https://en.wikipedia.org/wiki/Alan_Perlis",
        "color": 0x16A085
    },
    {
        "quote": "Simplicity does not precede complexity, but follows it.",
        "author": "Alan J. Perlis",
        "bio": "First recipient of the Turing Award",
        "wiki": "https://en.wikipedia.org/wiki/Alan_Perlis",
        "color": 0x16A085
    },
    {
        "quote": "One man's constant is another man's variable.",
        "author": "Alan J. Perlis",
        "bio": "First recipient of the Turing Award",
        "wiki": "https://en.wikipedia.org/wiki/Alan_Perlis",
        "color": 0x16A085
    },
    {
        "quote": "Make it work, make it right, make it fast.",
        "author": "Kent Beck",
        "bio": "Creator of Extreme Programming and Test-Driven Development",
        "wiki": "https://en.wikipedia.org/wiki/Kent_Beck",
        "color": 0x27AE60
    },
    {
        "quote": "I'm not a great programmer; I'm just a good programmer with great habits.",
        "author": "Kent Beck",
        "bio": "Creator of Extreme Programming and Test-Driven Development",
        "wiki": "https://en.wikipedia.org/wiki/Kent_Beck",
        "color": 0x27AE60
    },
    {
        "quote": "Any fool can write code that a computer can understand. Good programmers write code that humans can understand.",
        "author": "Martin Fowler",
        "bio": "Software developer, author, and speaker",
        "wiki": "https://en.wikipedia.org/wiki/Martin_Fowler_(software_engineer)",
        "color": 0x2ECC71
    },
    {
        "quote": "When you feel the need to write a comment, first try to refactor the code so that any comment becomes superfluous.",
        "author": "Martin Fowler",
        "bio": "Software developer, author, and speaker",
        "wiki": "https://en.wikipedia.org/wiki/Martin_Fowler_(software_engineer)",
        "color": 0x2ECC71
    },
    {
        "quote": "I'm not a real programmer. I throw together things until it works then I move on. The real programmers will say 'Yeah it works but you're leaking memory everywhere.'",
        "author": "Rasmus Lerdorf",
        "bio": "Creator of PHP",
        "wiki": "https://en.wikipedia.org/wiki/Rasmus_Lerdorf",
        "color": 0x777BB4  # PHP purple
    },
    {
        "quote": "PHP is about as exciting as your toothbrush. You use it every day, it does the job, it is a simple tool, so what? Who would want to read about toothbrushes?",
        "author": "Rasmus Lerdorf",
        "bio": "Creator of PHP",
        "wiki": "https://en.wikipedia.org/wiki/Rasmus_Lerdorf",
        "color": 0x777BB4
    },
    {
        "quote": "The proper use of comments is to compensate for our failure to express ourself in code.",
        "author": "Robert C. Martin",
        "bio": "Software engineer, author of 'Clean Code'",
        "wiki": "https://en.wikipedia.org/wiki/Robert_C._Martin",
        "color": 0x2ECC71
    },
    {
        "quote": "Code never lies, comments sometimes do.",
        "author": "Ron Jeffries",
        "bio": "Co-founder of Extreme Programming",
        "wiki": "https://en.wikipedia.org/wiki/Ron_Jeffries",
        "color": 0x27AE60
    },
    {
        "quote": "The best comment is a good variable name.",
        "author": "Anonymous",
        "bio": "Programming wisdom",
        "wiki": None,
        "color": 0x95A5A6
    },
    {
        "quote": "In programming, the hard part isn't solving problems, but deciding what problems to solve.",
        "author": "Paul Graham",
        "bio": "Programmer, writer, and co-founder of Y Combinator",
        "wiki": "https://en.wikipedia.org/wiki/Paul_Graham_(programmer)",
        "color": 0xFF6600  # Y Combinator orange
    },
    {
        "quote": "If you can't explain something in simple terms, you don't understand it.",
        "author": "Paul Graham",
        "bio": "Programmer, writer, and co-founder of Y Combinator",
        "wiki": "https://en.wikipedia.org/wiki/Paul_Graham_(programmer)",
        "color": 0xFF6600
    },
    {
        "quote": "A startup is a company designed to grow fast.",
        "author": "Paul Graham",
        "bio": "Programmer, writer, and co-founder of Y Combinator",
        "wiki": "https://en.wikipedia.org/wiki/Paul_Graham_(programmer)",
        "color": 0xFF6600
    },
    {
        "quote": "The way to get startup ideas is not to try to think of startup ideas. It's to look for problems, preferably problems you have yourself.",
        "author": "Paul Graham",
        "bio": "Programmer, writer, and co-founder of Y Combinator",
        "wiki": "https://en.wikipedia.org/wiki/Paul_Graham_(programmer)",
        "color": 0xFF6600
    },
    {
        "quote": "At every step the vast majority of emails are spam.",
        "author": "Bill Gates",
        "bio": "Co-founder of Microsoft",
        "wiki": "https://en.wikipedia.org/wiki/Bill_Gates",
        "color": 0x00A4EF
    },
    {
        "quote": "Don't compare yourself with anyone in this world. If you do so, you are insulting yourself.",
        "author": "Bill Gates",
        "bio": "Co-founder of Microsoft",
        "wiki": "https://en.wikipedia.org/wiki/Bill_Gates",
        "color": 0x00A4EF
    },
    {
        "quote": "It's not about ideas. It's about making ideas happen.",
        "author": "Scott Belsky",
        "bio": "Entrepreneur, author of 'Making Ideas Happen'",
        "wiki": "https://en.wikipedia.org/wiki/Scott_Belsky",
        "color": 0x9B59B6
    },
    {
        "quote": "Move fast and break things. Unless you are breaking stuff, you are not moving fast enough.",
        "author": "Mark Zuckerberg",
        "bio": "Co-founder and CEO of Facebook/Meta",
        "wiki": "https://en.wikipedia.org/wiki/Mark_Zuckerberg",
        "color": 0x4267B2  # Facebook blue
    },
    {
        "quote": "Ideas don't come out fully formed. They only become clear as you work on them. You just have to get started.",
        "author": "Mark Zuckerberg",
        "bio": "Co-founder and CEO of Facebook/Meta",
        "wiki": "https://en.wikipedia.org/wiki/Mark_Zuckerberg",
        "color": 0x4267B2
    },
    {
        "quote": "The biggest risk is not taking any risk. In a world that's changing really quickly, the only strategy that is guaranteed to fail is not taking risks.",
        "author": "Mark Zuckerberg",
        "bio": "Co-founder and CEO of Facebook/Meta",
        "wiki": "https://en.wikipedia.org/wiki/Mark_Zuckerberg",
        "color": 0x4267B2
    },
    {
        "quote": "Done is better than perfect.",
        "author": "Sheryl Sandberg",
        "bio": "Former COO of Facebook",
        "wiki": "https://en.wikipedia.org/wiki/Sheryl_Sandberg",
        "color": 0x4267B2
    },
    {
        "quote": "If you're not embarrassed by the first version of your product, you've launched too late.",
        "author": "Reid Hoffman",
        "bio": "Co-founder of LinkedIn",
        "wiki": "https://en.wikipedia.org/wiki/Reid_Hoffman",
        "color": 0x0077B5  # LinkedIn blue
    },
    {
        "quote": "An entrepreneur is someone who will jump off a cliff and assemble an airplane on the way down.",
        "author": "Reid Hoffman",
        "bio": "Co-founder of LinkedIn",
        "wiki": "https://en.wikipedia.org/wiki/Reid_Hoffman",
        "color": 0x0077B5
    },
    {
        "quote": "First, solve the problem. Then, write the code.",
        "author": "John Johnson",
        "bio": "Software developer",
        "wiki": None,
        "color": 0x3498DB
    },
    {
        "quote": "Experience is the name everyone gives to their mistakes.",
        "author": "Oscar Wilde",
        "bio": "Irish poet and playwright (often applied to programming)",
        "wiki": "https://en.wikipedia.org/wiki/Oscar_Wilde",
        "color": 0x9B59B6
    },
    {
        "quote": "In order to understand recursion, one must first understand recursion.",
        "author": "Anonymous",
        "bio": "Computer science humor",
        "wiki": None,
        "color": 0xE67E22
    },
    {
        "quote": "There are only two kinds of programming languages: those people always bitch about and those nobody uses.",
        "author": "Bjarne Stroustrup",
        "bio": "Creator of C++",
        "wiki": "https://en.wikipedia.org/wiki/Bjarne_Stroustrup",
        "color": 0x00599C
    },
    {
        "quote": "Clearly, I reject the view that there is one way that is right for everyone and for every problem.",
        "author": "Bjarne Stroustrup",
        "bio": "Creator of C++",
        "wiki": "https://en.wikipedia.org/wiki/Bjarne_Stroustrup",
        "color": 0x00599C
    },
    {
        "quote": "Destructors for virtual base classes are executed in the reverse order of their appearance in a depth-first left-to-right traversal of the directed acyclic graph of base classes.",
        "author": "Bjarne Stroustrup",
        "bio": "Creator of C++ (demonstrating C++ complexity)",
        "wiki": "https://en.wikipedia.org/wiki/Bjarne_Stroustrup",
        "color": 0x00599C
    },
    {
        "quote": "I have always wished for my computer to be as easy to use as my telephone; my wish has come true because I can no longer figure out how to use my telephone.",
        "author": "Bjarne Stroustrup",
        "bio": "Creator of C++",
        "wiki": "https://en.wikipedia.org/wiki/Bjarne_Stroustrup",
        "color": 0x00599C
    },
    {
        "quote": "C++ is a horrible language. It's made more horrible by the fact that a lot of substandard programmers use it.",
        "author": "Linus Torvalds",
        "bio": "Creator of Linux and Git",
        "wiki": "https://en.wikipedia.org/wiki/Linus_Torvalds",
        "color": 0xFCC624
    },
    {
        "quote": "Being abstract is something profoundly different from being vague... The purpose of abstraction is not to be vague, but to create a new semantic level in which one can be absolutely precise.",
        "author": "Edsger Dijkstra",
        "bio": "Computer scientist and pioneer of structured programming",
        "wiki": "https://en.wikipedia.org/wiki/Edsger_W._Dijkstra",
        "color": 0x34495E
    },
    {
        "quote": "The use of COBOL cripples the mind; its teaching should, therefore, be regarded as a criminal offense.",
        "author": "Edsger Dijkstra",
        "bio": "Computer scientist and pioneer of structured programming",
        "wiki": "https://en.wikipedia.org/wiki/Edsger_W._Dijkstra",
        "color": 0x34495E
    },
    {
        "quote": "Object-oriented programming is an exceptionally bad idea which could only have originated in California.",
        "author": "Edsger Dijkstra",
        "bio": "Computer scientist and pioneer of structured programming",
        "wiki": "https://en.wikipedia.org/wiki/Edsger_W._Dijkstra",
        "color": 0x34495E
    },
    {
        "quote": "It is practically impossible to teach good programming to students that have had a prior exposure to BASIC: as potential programmers they are mentally mutilated beyond hope of regeneration.",
        "author": "Edsger Dijkstra",
        "bio": "Computer scientist and pioneer of structured programming",
        "wiki": "https://en.wikipedia.org/wiki/Edsger_W._Dijkstra",
        "color": 0x34495E
    },
    {
        "quote": "Program testing can be used to show the presence of bugs, but never to show their absence!",
        "author": "Edsger Dijkstra",
        "bio": "Computer scientist and pioneer of structured programming",
        "wiki": "https://en.wikipedia.org/wiki/Edsger_W._Dijkstra",
        "color": 0x34495E
    },
    {
        "quote": "The computing scientist's main challenge is not to get confused by the complexities of his own making.",
        "author": "Edsger Dijkstra",
        "bio": "Computer scientist and pioneer of structured programming",
        "wiki": "https://en.wikipedia.org/wiki/Edsger_W._Dijkstra",
        "color": 0x34495E
    },
    {
        "quote": "If you don't fail at least 90% of the time, you're not aiming high enough.",
        "author": "Alan Kay",
        "bio": "Computer scientist, pioneer of object-oriented programming",
        "wiki": "https://en.wikipedia.org/wiki/Alan_Kay",
        "color": 0x3498DB
    },
    {
        "quote": "The best way to predict the future is to invent it.",
        "author": "Alan Kay",
        "bio": "Computer scientist, pioneer of object-oriented programming",
        "wiki": "https://en.wikipedia.org/wiki/Alan_Kay",
        "color": 0x3498DB
    },
    {
        "quote": "Simple things should be simple, complex things should be possible.",
        "author": "Alan Kay",
        "bio": "Computer scientist, pioneer of object-oriented programming",
        "wiki": "https://en.wikipedia.org/wiki/Alan_Kay",
        "color": 0x3498DB
    },
    {
        "quote": "Technology is anything that wasn't around when you were born.",
        "author": "Alan Kay",
        "bio": "Computer scientist, pioneer of object-oriented programming",
        "wiki": "https://en.wikipedia.org/wiki/Alan_Kay",
        "color": 0x3498DB
    },
    {
        "quote": "Most software today is very much like an Egyptian pyramid with millions of bricks piled on top of each other, with no structural integrity, but just done by brute force and thousands of slaves.",
        "author": "Alan Kay",
        "bio": "Computer scientist, pioneer of object-oriented programming",
        "wiki": "https://en.wikipedia.org/wiki/Alan_Kay",
        "color": 0x3498DB
    },
    {
        "quote": "The prototyping problem: when the prototype becomes the product.",
        "author": "Anonymous",
        "bio": "Software development reality",
        "wiki": None,
        "color": 0xE74C3C
    },
    {
        "quote": "There is nothing quite so permanent as a temporary solution.",
        "author": "Anonymous",
        "bio": "Software development wisdom",
        "wiki": None,
        "color": 0xC0392B
    },
    {
        "quote": "The trouble with programmers is that you can never tell what a programmer is doing until it's too late.",
        "author": "Seymour Cray",
        "bio": "Supercomputer architect",
        "wiki": "https://en.wikipedia.org/wiki/Seymour_Cray",
        "color": 0x2C3E50
    },
    {
        "quote": "Anyone who considers arithmetical methods of producing random digits is, of course, in a state of sin.",
        "author": "John von Neumann",
        "bio": "Mathematician and polymath, pioneer of computer science",
        "wiki": "https://en.wikipedia.org/wiki/John_von_Neumann",
        "color": 0x34495E
    },
    {
        "quote": "In mathematics you don't understand things. You just get used to them.",
        "author": "John von Neumann",
        "bio": "Mathematician and polymath, pioneer of computer science",
        "wiki": "https://en.wikipedia.org/wiki/John_von_Neumann",
        "color": 0x34495E
    },
    {
        "quote": "Young man, in mathematics you don't understand things. You just get used to them.",
        "author": "John von Neumann",
        "bio": "Mathematician and polymath, pioneer of computer science",
        "wiki": "https://en.wikipedia.org/wiki/John_von_Neumann",
        "color": 0x34495E
    },
    {
        "quote": "If people do not believe that mathematics is simple, it is only because they do not realize how complicated life is.",
        "author": "John von Neumann",
        "bio": "Mathematician and polymath, pioneer of computer science",
        "wiki": "https://en.wikipedia.org/wiki/John_von_Neumann",
        "color": 0x34495E
    },
    {
        "quote": "With four parameters I can fit an elephant, and with five I can make him wiggle his trunk.",
        "author": "John von Neumann",
        "bio": "Mathematician and polymath, pioneer of computer science",
        "wiki": "https://en.wikipedia.org/wiki/John_von_Neumann",
        "color": 0x34495E
    },
    {
        "quote": "Should array indices start at 0 or 1? My compromise of 0.5 was rejected without, I thought, proper consideration.",
        "author": "Stan Kelly-Bootle",
        "bio": "Computer scientist and humorist",
        "wiki": "https://en.wikipedia.org/wiki/Stan_Kelly-Bootle",
        "color": 0xE67E22
    },
    {
        "quote": "There are two ways of constructing a software design: One way is to make it so simple that there are obviously no deficiencies, and the other way is to make it so complicated that there are no obvious deficiencies.",
        "author": "C.A.R. Hoare",
        "bio": "Computer scientist, invented quicksort",
        "wiki": "https://en.wikipedia.org/wiki/Tony_Hoare",
        "color": 0x16A085
    },
    {
        "quote": "Premature optimization is the root of all evil.",
        "author": "C.A.R. Hoare",
        "bio": "Computer scientist, invented quicksort (popularized by Knuth)",
        "wiki": "https://en.wikipedia.org/wiki/Tony_Hoare",
        "color": 0x16A085
    },
    {
        "quote": "I call it my billion-dollar mistake. It was the invention of the null reference in 1965.",
        "author": "C.A.R. Hoare",
        "bio": "Computer scientist, invented quicksort",
        "wiki": "https://en.wikipedia.org/wiki/Tony_Hoare",
        "color": 0x16A085
    },
    {
        "quote": "Inside every large program is a small program trying to get out.",
        "author": "C.A.R. Hoare",
        "bio": "Computer scientist, invented quicksort",
        "wiki": "https://en.wikipedia.org/wiki/Tony_Hoare",
        "color": 0x16A085
    },
    {
        "quote": "You cannot teach beginners top-down programming, because they don't know which end is up.",
        "author": "C.A.R. Hoare",
        "bio": "Computer scientist, invented quicksort",
        "wiki": "https://en.wikipedia.org/wiki/Tony_Hoare",
        "color": 0x16A085
    },
    {
        "quote": "We should forget about small efficiencies, say about 97% of the time: premature optimization is the root of all evil. Yet we should not pass up our opportunities in that critical 3%.",
        "author": "Donald Knuth",
        "bio": "Author of 'The Art of Computer Programming'",
        "wiki": "https://en.wikipedia.org/wiki/Donald_Knuth",
        "color": 0x8B4513
    },
    {
        "quote": "Controlling complexity is the essence of computer programming.",
        "author": "Brian Kernighan",
        "bio": "Co-author of 'The C Programming Language'",
        "wiki": "https://en.wikipedia.org/wiki/Brian_Kernighan",
        "color": 0x555555
    },
    {
        "quote": "Everyone knows that debugging is twice as hard as writing a program in the first place. So if you're as clever as you can be when you write it, how will you ever debug it?",
        "author": "Brian Kernighan",
        "bio": "Co-author of 'The C Programming Language'",
        "wiki": "https://en.wikipedia.org/wiki/Brian_Kernighan",
        "color": 0x555555
    },
    {
        "quote": "The most effective debugging tool is still careful thought, coupled with judiciously placed print statements.",
        "author": "Brian Kernighan",
        "bio": "Co-author of 'The C Programming Language'",
        "wiki": "https://en.wikipedia.org/wiki/Brian_Kernighan",
        "color": 0x555555
    },
    {
        "quote": "Do what you think is interesting, do something that you think is fun and worthwhile, because otherwise you won't do it well anyway.",
        "author": "Brian Kernighan",
        "bio": "Co-author of 'The C Programming Language'",
        "wiki": "https://en.wikipedia.org/wiki/Brian_Kernighan",
        "color": 0x555555
    },
    {
        "quote": "The purpose of software engineering is to control complexity, not to create it.",
        "author": "Pamela Zave",
        "bio": "Computer scientist specializing in requirements engineering",
        "wiki": "https://en.wikipedia.org/wiki/Pamela_Zave",
        "color": 0x9B59B6
    },
    {
        "quote": "Walking on water and developing software from a specification are easy if both are frozen.",
        "author": "Edward V. Berard",
        "bio": "Software consultant and author",
        "wiki": None,
        "color": 0x3498DB
    },
    {
        "quote": "The most disastrous thing that you can ever learn is your first programming language.",
        "author": "Alan Kay",
        "bio": "Computer scientist, pioneer of object-oriented programming",
        "wiki": "https://en.wikipedia.org/wiki/Alan_Kay",
        "color": 0x3498DB
    },
    {
        "quote": "Perspective is worth 80 IQ points.",
        "author": "Alan Kay",
        "bio": "Computer scientist, pioneer of object-oriented programming",
        "wiki": "https://en.wikipedia.org/wiki/Alan_Kay",
        "color": 0x3498DB
    },
    {
        "quote": "It's easier to ask forgiveness than it is to get permission.",
        "author": "Grace Hopper",
        "bio": "Computer science pioneer, inventor of first compiler",
        "wiki": "https://en.wikipedia.org/wiki/Grace_Hopper",
        "color": 0xE91E63
    },
    {
        "quote": "The most damaging phrase in the language is: 'We've always done it this way.'",
        "author": "Grace Hopper",
        "bio": "Computer science pioneer, inventor of first compiler",
        "wiki": "https://en.wikipedia.org/wiki/Grace_Hopper",
        "color": 0xE91E63
    },
    {
        "quote": "To me programming is more than an important practical art. It is also a gigantic undertaking in the foundations of knowledge.",
        "author": "Grace Hopper",
        "bio": "Computer science pioneer, inventor of first compiler",
        "wiki": "https://en.wikipedia.org/wiki/Grace_Hopper",
        "color": 0xE91E63
    },
    {
        "quote": "If it's a good idea, go ahead and do it. It's much easier to apologize than it is to get permission.",
        "author": "Grace Hopper",
        "bio": "Computer science pioneer, inventor of first compiler",
        "wiki": "https://en.wikipedia.org/wiki/Grace_Hopper",
        "color": 0xE91E63
    },
    {
        "quote": "Humans are allergic to change. They love to say, 'We've always done it this way.' I try to fight that.",
        "author": "Grace Hopper",
        "bio": "Computer science pioneer, inventor of first compiler",
        "wiki": "https://en.wikipedia.org/wiki/Grace_Hopper",
        "color": 0xE91E63
    },
    {
        "quote": "Life was simple before World War II. After that, we had systems.",
        "author": "Grace Hopper",
        "bio": "Computer science pioneer, inventor of first compiler",
        "wiki": "https://en.wikipedia.org/wiki/Grace_Hopper",
        "color": 0xE91E63
    },
    {
        "quote": "One accurate measurement is worth a thousand expert opinions.",
        "author": "Grace Hopper",
        "bio": "Computer science pioneer, inventor of first compiler",
        "wiki": "https://en.wikipedia.org/wiki/Grace_Hopper",
        "color": 0xE91E63
    },
    {
        "quote": "A ship in port is safe, but that's not what ships are built for.",
        "author": "Grace Hopper",
        "bio": "Computer science pioneer, inventor of first compiler",
        "wiki": "https://en.wikipedia.org/wiki/Grace_Hopper",
        "color": 0xE91E63
    },
    {
        "quote": "From then on, when anything went wrong with a computer, we said it had bugs in it.",
        "author": "Grace Hopper",
        "bio": "Computer science pioneer, inventor of first compiler",
        "wiki": "https://en.wikipedia.org/wiki/Grace_Hopper",
        "color": 0xE91E63
    },
    {
        "quote": "Always aim for achievement, and forget about success.",
        "author": "Helen Hayes",
        "bio": "Actress (often quoted in tech contexts)",
        "wiki": "https://en.wikipedia.org/wiki/Helen_Hayes",
        "color": 0x9B59B6
    },
    {
        "quote": "Programs must be written for people to read, and only incidentally for machines to execute.",
        "author": "Hal Abelson",
        "bio": "Computer scientist, co-author of 'Structure and Interpretation of Computer Programs'",
        "wiki": "https://en.wikipedia.org/wiki/Hal_Abelson",
        "color": 0x9B27B0
    },
    {
        "quote": "Lisp isn't a language, it's a building material.",
        "author": "Alan Kay",
        "bio": "Computer scientist, pioneer of object-oriented programming",
        "wiki": "https://en.wikipedia.org/wiki/Alan_Kay",
        "color": 0x3498DB
    },
    {
        "quote": "Lisp has jokingly been called 'the most intelligent way to misuse a computer'. I think that description is a great compliment.",
        "author": "Edsger Dijkstra",
        "bio": "Computer scientist and pioneer of structured programming",
        "wiki": "https://en.wikipedia.org/wiki/Edsger_W._Dijkstra",
        "color": 0x34495E
    },
    {
        "quote": "The function of good software is to make the complex appear to be simple.",
        "author": "Grady Booch",
        "bio": "Software engineer, developed UML",
        "wiki": "https://en.wikipedia.org/wiki/Grady_Booch",
        "color": 0x16A085
    },
    {
        "quote": "The amateur software engineer is always in search of magic.",
        "author": "Grady Booch",
        "bio": "Software engineer, developed UML",
        "wiki": "https://en.wikipedia.org/wiki/Grady_Booch",
        "color": 0x16A085
    },
    {
        "quote": "A primary cause of complexity is that software vendors uncritically adopt almost any feature that users want.",
        "author": "Niklaus Wirth",
        "bio": "Computer scientist, creator of Pascal",
        "wiki": "https://en.wikipedia.org/wiki/Niklaus_Wirth",
        "color": 0x2E7D32
    },
    {
        "quote": "Software is getting slower more rapidly than hardware becomes faster.",
        "author": "Niklaus Wirth",
        "bio": "Computer scientist, creator of Pascal (Wirth's Law)",
        "wiki": "https://en.wikipedia.org/wiki/Niklaus_Wirth",
        "color": 0x2E7D32
    },
    {
        "quote": "A good programming language is a conceptual universe for thinking about programming.",
        "author": "Niklaus Wirth",
        "bio": "Computer scientist, creator of Pascal",
        "wiki": "https://en.wikipedia.org/wiki/Niklaus_Wirth",
        "color": 0x2E7D32
    },
    {
        "quote": "But active programming consists of the design of new programs, rather than contemplation of old programs.",
        "author": "Niklaus Wirth",
        "bio": "Computer scientist, creator of Pascal",
        "wiki": "https://en.wikipedia.org/wiki/Niklaus_Wirth",
        "color": 0x2E7D32
    },
    {
        "quote": "Increasingly, people seem to misinterpret complexity as sophistication, which is baffling.",
        "author": "Niklaus Wirth",
        "bio": "Computer scientist, creator of Pascal",
        "wiki": "https://en.wikipedia.org/wiki/Niklaus_Wirth",
        "color": 0x2E7D32
    },
    {
        "quote": "The best book on programming for the layman is 'Alice in Wonderland'; but that's because it's the best book on anything for the layman.",
        "author": "Alan J. Perlis",
        "bio": "First recipient of the Turing Award",
        "wiki": "https://en.wikipedia.org/wiki/Alan_Perlis",
        "color": 0x16A085
    },
    {
        "quote": "When someone says 'I want a programming language in which I need only say what I wish done,' give him a lollipop.",
        "author": "Alan J. Perlis",
        "bio": "First recipient of the Turing Award",
        "wiki": "https://en.wikipedia.org/wiki/Alan_Perlis",
        "color": 0x16A085
    },
    {
        "quote": "A programming language is low level when its programs require attention to the irrelevant.",
        "author": "Alan J. Perlis",
        "bio": "First recipient of the Turing Award",
        "wiki": "https://en.wikipedia.org/wiki/Alan_Perlis",
        "color": 0x16A085
    },
    {
        "quote": "Syntactic sugar causes cancer of the semicolon.",
        "author": "Alan J. Perlis",
        "bio": "First recipient of the Turing Award",
        "wiki": "https://en.wikipedia.org/wiki/Alan_Perlis",
        "color": 0x16A085
    },
    {
        "quote": "It is easier to write an incorrect program than understand a correct one.",
        "author": "Alan J. Perlis",
        "bio": "First recipient of the Turing Award",
        "wiki": "https://en.wikipedia.org/wiki/Alan_Perlis",
        "color": 0x16A085
    },
    {
        "quote": "Adapting old programs to fit new machines usually means adapting new machines to behave like old ones.",
        "author": "Alan J. Perlis",
        "bio": "First recipient of the Turing Award",
        "wiki": "https://en.wikipedia.org/wiki/Alan_Perlis",
        "color": 0x16A085
    },
    {
        "quote": "Some programming languages manage to absorb change, but withstand progress.",
        "author": "Alan J. Perlis",
        "bio": "First recipient of the Turing Award",
        "wiki": "https://en.wikipedia.org/wiki/Alan_Perlis",
        "color": 0x16A085
    },
    {
        "quote": "You think you know when you can learn, are more sure when you can write, even more when you can teach, but certain when you can program.",
        "author": "Alan J. Perlis",
        "bio": "First recipient of the Turing Award",
        "wiki": "https://en.wikipedia.org/wiki/Alan_Perlis",
        "color": 0x16A085
    },
    {
        "quote": "To understand a program you must become both the machine and the program.",
        "author": "Alan J. Perlis",
        "bio": "First recipient of the Turing Award",
        "wiki": "https://en.wikipedia.org/wiki/Alan_Perlis",
        "color": 0x16A085
    },
    {
        "quote": "If a listener nods his head when you're explaining your program, wake him up.",
        "author": "Alan J. Perlis",
        "bio": "First recipient of the Turing Award",
        "wiki": "https://en.wikipedia.org/wiki/Alan_Perlis",
        "color": 0x16A085
    },
    {
        "quote": "In theory, theory and practice are the same. In practice, they're not.",
        "author": "Yogi Berra",
        "bio": "Baseball player (often applied to programming)",
        "wiki": "https://en.wikipedia.org/wiki/Yogi_Berra",
        "color": 0xE67E22
    },
    {
        "quote": "Code is like humor. When you have to explain it, it's bad.",
        "author": "Cory House",
        "bio": "Software architect and author",
        "wiki": None,
        "color": 0x3498DB
    },
    {
        "quote": "Programming isn't about what you know; it's about what you can figure out.",
        "author": "Chris Pine",
        "bio": "Programmer and author",
        "wiki": None,
        "color": 0x27AE60
    },
    {
        "quote": "The computer was born to solve problems that did not exist before.",
        "author": "Bill Gates",
        "bio": "Co-founder of Microsoft",
        "wiki": "https://en.wikipedia.org/wiki/Bill_Gates",
        "color": 0x00A4EF
    },
    {
        "quote": "Sometimes it pays to stay in bed on Monday, rather than spending the rest of the week debugging Monday's code.",
        "author": "Dan Salomon",
        "bio": "Software developer",
        "wiki": None,
        "color": 0xE74C3C
    },
    {
        "quote": "Code without tests is bad code. It doesn't matter how well written it is; it doesn't matter how pretty or object-oriented or well-encapsulated it is. With tests, we can change the behavior of our code quickly and verifiably. Without them, we really don't know if our code is getting better or worse.",
        "author": "Michael Feathers",
        "bio": "Author of 'Working Effectively with Legacy Code'",
        "wiki": "https://en.wikipedia.org/wiki/Michael_Feathers",
        "color": 0x2ECC71
    },
    {
        "quote": "Every great developer you know got there by solving problems they were unqualified to solve until they actually did it.",
        "author": "Patrick McKenzie",
        "bio": "Software developer and entrepreneur",
        "wiki": None,
        "color": 0x9B59B6
    },
    {
        "quote": "The best error message is the one that never shows up.",
        "author": "Thomas Fuchs",
        "bio": "Developer and creator of Script.aculo.us",
        "wiki": "https://en.wikipedia.org/wiki/Thomas_Fuchs_(programmer)",
        "color": 0x3498DB
    },
    {
        "quote": "Weeks of coding can save you hours of planning.",
        "author": "Anonymous",
        "bio": "Software development wisdom",
        "wiki": None,
        "color": 0xC0392B
    },
    {
        "quote": "Debugging is like being the detective in a crime movie where you are also the murderer.",
        "author": "Filipe Fortes",
        "bio": "Software engineer",
        "wiki": None,
        "color": 0xE74C3C
    },
    {
        "quote": "I'm not a great programmer; I'm just a good programmer with great habits.",
        "author": "Martin Fowler",
        "bio": "Software developer, author, and speaker",
        "wiki": "https://en.wikipedia.org/wiki/Martin_Fowler_(software_engineer)",
        "color": 0x2ECC71
    },
    {
        "quote": "The only way to learn a new programming language is by writing programs in it.",
        "author": "Dennis Ritchie",
        "bio": "Creator of the C programming language",
        "wiki": "https://en.wikipedia.org/wiki/Dennis_Ritchie",
        "color": 0x555555
    },
    {
        "quote": "Unix is simple. It just takes a genius to understand its simplicity.",
        "author": "Dennis Ritchie",
        "bio": "Creator of the C programming language",
        "wiki": "https://en.wikipedia.org/wiki/Dennis_Ritchie",
        "color": 0x555555
    },
    {
        "quote": "C is quirky, flawed, and an enormous success.",
        "author": "Dennis Ritchie",
        "bio": "Creator of the C programming language",
        "wiki": "https://en.wikipedia.org/wiki/Dennis_Ritchie",
        "color": 0x555555
    },
    {
        "quote": "The cheapest, fastest, and most reliable components are those that aren't there.",
        "author": "Gordon Bell",
        "bio": "Computer engineer",
        "wiki": "https://en.wikipedia.org/wiki/Gordon_Bell",
        "color": 0x34495E
    },
    {
        "quote": "One of my most productive days was throwing away 1,000 lines of code.",
        "author": "Ken Thompson",
        "bio": "Creator of Unix",
        "wiki": "https://en.wikipedia.org/wiki/Ken_Thompson",
        "color": 0x34495E
    },
    {
        "quote": "When in doubt, use brute force.",
        "author": "Ken Thompson",
        "bio": "Creator of Unix",
        "wiki": "https://en.wikipedia.org/wiki/Ken_Thompson",
        "color": 0x34495E
    },
    {
        "quote": "You can't trust code that you did not totally create yourself.",
        "author": "Ken Thompson",
        "bio": "Creator of Unix",
        "wiki": "https://en.wikipedia.org/wiki/Ken_Thompson",
        "color": 0x34495E
    },
    {
        "quote": "No matter how slick the demo is in rehearsal, when you do it in front of a live audience, the probability of a flawless presentation is inversely proportional to the number of people watching, raised to the power of the amount of money involved.",
        "author": "Mark Gibbs",
        "bio": "Technology journalist",
        "wiki": None,
        "color": 0xE74C3C
    },
    {
        "quote": "Software undergoes beta testing shortly before it's released. Beta is Latin for 'still doesn't work.'",
        "author": "Anonymous",
        "bio": "Tech humor",
        "wiki": None,
        "color": 0xF39C12
    },
    {
        "quote": "Always code as if the guy who ends up maintaining your code will be a violent psychopath who knows where you live.",
        "author": "John Woods",
        "bio": "comp.lang.c++ moderator",
        "wiki": None,
        "color": 0xC0392B
    },
    {
        "quote": "Good code is its own best documentation.",
        "author": "Steve McConnell",
        "bio": "Author of 'Code Complete'",
        "wiki": "https://en.wikipedia.org/wiki/Steve_McConnell",
        "color": 0x2ECC71
    },
    {
        "quote": "It's OK to figure out murder mysteries, but you shouldn't need to figure out code. You should be able to read it.",
        "author": "Steve McConnell",
        "bio": "Author of 'Code Complete'",
        "wiki": "https://en.wikipedia.org/wiki/Steve_McConnell",
        "color": 0x2ECC71
    },
    {
        "quote": "Trying to improve software quality by increasing the amount of testing is like trying to lose weight by weighing yourself more often.",
        "author": "Steve McConnell",
        "bio": "Author of 'Code Complete'",
        "wiki": "https://en.wikipedia.org/wiki/Steve_McConnell",
        "color": 0x2ECC71
    },
    {
        "quote": "The first 90% of the code accounts for the first 90% of the development time. The remaining 10% of the code accounts for the other 90% of the development time.",
        "author": "Tom Cargill",
        "bio": "Software engineer (The Ninety-ninety rule)",
        "wiki": None,
        "color": 0xE74C3C
    },
    {
        "quote": "Good judgment comes from experience, and experience comes from bad judgment.",
        "author": "Fred Brooks",
        "bio": "Computer scientist, author of 'The Mythical Man-Month'",
        "wiki": "https://en.wikipedia.org/wiki/Fred_Brooks",
        "color": 0x34495E
    },
    {
        "quote": "Plan to throw one away; you will, anyhow.",
        "author": "Fred Brooks",
        "bio": "Computer scientist, author of 'The Mythical Man-Month'",
        "wiki": "https://en.wikipedia.org/wiki/Fred_Brooks",
        "color": 0x34495E
    },
    {
        "quote": "The bearing of a child takes nine months, no matter how many women are assigned.",
        "author": "Fred Brooks",
        "bio": "Computer scientist, author of 'The Mythical Man-Month'",
        "wiki": "https://en.wikipedia.org/wiki/Fred_Brooks",
        "color": 0x34495E
    },
    {
        "quote": "How does a project get to be a year late? One day at a time.",
        "author": "Fred Brooks",
        "bio": "Computer scientist, author of 'The Mythical Man-Month'",
        "wiki": "https://en.wikipedia.org/wiki/Fred_Brooks",
        "color": 0x34495E
    },
    {
        "quote": "The programmer, like the poet, works only slightly removed from pure thought-stuff. He builds his castles in the air, from air, creating by exertion of the imagination.",
        "author": "Fred Brooks",
        "bio": "Computer scientist, author of 'The Mythical Man-Month'",
        "wiki": "https://en.wikipedia.org/wiki/Fred_Brooks",
        "color": 0x34495E
    },
    {
        "quote": "Show me your flowcharts and conceal your tables, and I shall continue to be mystified. Show me your tables, and I won't usually need your flowcharts; they'll be obvious.",
        "author": "Fred Brooks",
        "bio": "Computer scientist, author of 'The Mythical Man-Month'",
        "wiki": "https://en.wikipedia.org/wiki/Fred_Brooks",
        "color": 0x34495E
    },
    {
        "quote": "Einstein argued that there must be simplified explanations of nature, because God is not capricious or arbitrary. No such faith comforts the software engineer.",
        "author": "Fred Brooks",
        "bio": "Computer scientist, author of 'The Mythical Man-Month'",
        "wiki": "https://en.wikipedia.org/wiki/Fred_Brooks",
        "color": 0x34495E
    },
    {
        "quote": "There is no single development, in either technology or management technique, which by itself promises even one order of magnitude improvement within a decade in productivity, in reliability, in simplicity.",
        "author": "Fred Brooks",
        "bio": "Computer scientist, author of 'The Mythical Man-Month'",
        "wiki": "https://en.wikipedia.org/wiki/Fred_Brooks",
        "color": 0x34495E
    },
    {
        "quote": "The hardest single part of building a software system is deciding precisely what to build.",
        "author": "Fred Brooks",
        "bio": "Computer scientist, author of 'The Mythical Man-Month'",
        "wiki": "https://en.wikipedia.org/wiki/Fred_Brooks",
        "color": 0x34495E
    },
    {
        "quote": "Much of the essence of building a program is in fact the debugging of the specification.",
        "author": "Fred Brooks",
        "bio": "Computer scientist, author of 'The Mythical Man-Month'",
        "wiki": "https://en.wikipedia.org/wiki/Fred_Brooks",
        "color": 0x34495E
    },
    {
        "quote": "You know you're brilliant, but maybe you'd like to understand what you did 2 weeks from now.",
        "author": "Linus Torvalds",
        "bio": "Creator of Linux and Git",
        "wiki": "https://en.wikipedia.org/wiki/Linus_Torvalds",
        "color": 0xFCC624
    },
    {
        "quote": "Don't comment bad code—rewrite it.",
        "author": "Brian Kernighan",
        "bio": "Co-author of 'The C Programming Language'",
        "wiki": "https://en.wikipedia.org/wiki/Brian_Kernighan",
        "color": 0x555555
    },
    {
        "quote": "Code should be written to minimize the time it would take for someone else to understand it.",
        "author": "Dustin Boswell",
        "bio": "Author of 'The Art of Readable Code'",
        "wiki": None,
        "color": 0x3498DB
    },
    {
        "quote": "Programming is not a zero-sum game. Teaching something to a fellow programmer doesn't take it away from you.",
        "author": "John Carmack",
        "bio": "Game developer, co-founder of id Software",
        "wiki": "https://en.wikipedia.org/wiki/John_Carmack",
        "color": 0xE74C3C
    },
    {
        "quote": "Focused, hard work is the real key to success. Keep your eyes on the goal, and just keep taking the next step towards completing it.",
        "author": "John Carmack",
        "bio": "Game developer, co-founder of id Software",
        "wiki": "https://en.wikipedia.org/wiki/John_Carmack",
        "color": 0xE74C3C
    },
    {
        "quote": "Story in a game is like a story in a porn movie. It's expected to be there, but it's not that important.",
        "author": "John Carmack",
        "bio": "Game developer, co-founder of id Software",
        "wiki": "https://en.wikipedia.org/wiki/John_Carmack",
        "color": 0xE74C3C
    },
    {
        "quote": "Low-level programming is good for the programmer's soul.",
        "author": "John Carmack",
        "bio": "Game developer, co-founder of id Software",
        "wiki": "https://en.wikipedia.org/wiki/John_Carmack",
        "color": 0xE74C3C
    },
    {
        "quote": "It's done when it's done.",
        "author": "Shigeru Miyamoto",
        "bio": "Video game designer at Nintendo",
        "wiki": "https://en.wikipedia.org/wiki/Shigeru_Miyamoto",
        "color": 0xE60012  # Nintendo red
    },
    {
        "quote": "A delayed game is eventually good, but a rushed game is forever bad.",
        "author": "Shigeru Miyamoto",
        "bio": "Video game designer at Nintendo",
        "wiki": "https://en.wikipedia.org/wiki/Shigeru_Miyamoto",
        "color": 0xE60012
    },
    {
        "quote": "Video games are bad for you? That's what they said about rock and roll.",
        "author": "Shigeru Miyamoto",
        "bio": "Video game designer at Nintendo",
        "wiki": "https://en.wikipedia.org/wiki/Shigeru_Miyamoto",
        "color": 0xE60012
    },
    {
        "quote": "I think that inside every adult is the heart of a child. We just gradually convince ourselves that we have to act more like adults.",
        "author": "Shigeru Miyamoto",
        "bio": "Video game designer at Nintendo",
        "wiki": "https://en.wikipedia.org/wiki/Shigeru_Miyamoto",
        "color": 0xE60012
    },
    {
        "quote": "Throughout the Zelda series I've always tried to make players feel like they are in a kind of miniature garden. So users can enjoy fresh and unexpected surprises.",
        "author": "Shigeru Miyamoto",
        "bio": "Video game designer at Nintendo",
        "wiki": "https://en.wikipedia.org/wiki/Shigeru_Miyamoto",
        "color": 0xE60012
    },
    {
        "quote": "What I'm really excited about is that continued challenge to create things that gamers of all experiences can play.",
        "author": "Shigeru Miyamoto",
        "bio": "Video game designer at Nintendo",
        "wiki": "https://en.wikipedia.org/wiki/Shigeru_Miyamoto",
        "color": 0xE60012
    },
    {
        "quote": "The role of a creative leader is not to have all the ideas; it's to create a culture where everyone can have ideas and feel that they're valued.",
        "author": "Ken Robinson",
        "bio": "Author and creativity expert",
        "wiki": "https://en.wikipedia.org/wiki/Ken_Robinson_(educationalist)",
        "color": 0x9B59B6
    },
    {
        "quote": "Perl – The only language that looks the same before and after RSA encryption.",
        "author": "Keith Bostic",
        "bio": "Software engineer",
        "wiki": "https://en.wikipedia.org/wiki/Keith_Bostic",
        "color": 0x39457E  # Perl blue
    },
    {
        "quote": "Perl is designed to give you several ways to do anything, so consider picking the most readable one.",
        "author": "Larry Wall",
        "bio": "Creator of Perl",
        "wiki": "https://en.wikipedia.org/wiki/Larry_Wall",
        "color": 0x39457E
    },
    {
        "quote": "Real programmers can write assembly code in any language.",
        "author": "Larry Wall",
        "bio": "Creator of Perl",
        "wiki": "https://en.wikipedia.org/wiki/Larry_Wall",
        "color": 0x39457E
    },
    {
        "quote": "The three chief virtues of a programmer are: Laziness, Impatience and Hubris.",
        "author": "Larry Wall",
        "bio": "Creator of Perl",
        "wiki": "https://en.wikipedia.org/wiki/Larry_Wall",
        "color": 0x39457E
    },
    {
        "quote": "Most of you are familiar with the virtues of a programmer. There are three, of course: laziness, impatience, and hubris.",
        "author": "Larry Wall",
        "bio": "Creator of Perl",
        "wiki": "https://en.wikipedia.org/wiki/Larry_Wall",
        "color": 0x39457E
    },
    {
        "quote": "We all agree on the necessity of compromise. We just can't agree on when it's necessary to compromise.",
        "author": "Larry Wall",
        "bio": "Creator of Perl",
        "wiki": "https://en.wikipedia.org/wiki/Larry_Wall",
        "color": 0x39457E
    },
    {
        "quote": "Doing linear scans over an associative array is like trying to club someone to death with a loaded Uzi.",
        "author": "Larry Wall",
        "bio": "Creator of Perl",
        "wiki": "https://en.wikipedia.org/wiki/Larry_Wall",
        "color": 0x39457E
    },
    {
        "quote": "Somebody out there was about to find out that Perl is a little bit like Lisp, a little bit like C, and a lot like Unix.",
        "author": "Larry Wall",
        "bio": "Creator of Perl",
        "wiki": "https://en.wikipedia.org/wiki/Larry_Wall",
        "color": 0x39457E
    },
    {
        "quote": "I want to see Christianity spelled with a capital C and an exclamation mark at the end. But I also want to see it spelled with a small c and a question mark inside the soul of a person.",
        "author": "Larry Wall",
        "bio": "Creator of Perl",
        "wiki": "https://en.wikipedia.org/wiki/Larry_Wall",
        "color": 0x39457E
    },
    {
        "quote": "The trouble with computers is that you 'play' with them!",
        "author": "Richard Feynman",
        "bio": "Physicist and Nobel laureate",
        "wiki": "https://en.wikipedia.org/wiki/Richard_Feynman",
        "color": 0x3498DB
    },
    {
        "quote": "What I cannot create, I do not understand.",
        "author": "Richard Feynman",
        "bio": "Physicist and Nobel laureate",
        "wiki": "https://en.wikipedia.org/wiki/Richard_Feynman",
        "color": 0x3498DB
    },
    {
        "quote": "The first principle is that you must not fool yourself and you are the easiest person to fool.",
        "author": "Richard Feynman",
        "bio": "Physicist and Nobel laureate",
        "wiki": "https://en.wikipedia.org/wiki/Richard_Feynman",
        "color": 0x3498DB
    },
    {
        "quote": "I would rather have questions that can't be answered than answers that can't be questioned.",
        "author": "Richard Feynman",
        "bio": "Physicist and Nobel laureate",
        "wiki": "https://en.wikipedia.org/wiki/Richard_Feynman",
        "color": 0x3498DB
    },
    {
        "quote": "Study hard what interests you the most in the most undisciplined, irreverent and original manner possible.",
        "author": "Richard Feynman",
        "bio": "Physicist and Nobel laureate",
        "wiki": "https://en.wikipedia.org/wiki/Richard_Feynman",
        "color": 0x3498DB
    },
    {
        "quote": "It doesn't matter how beautiful your theory is, it doesn't matter how smart you are. If it doesn't agree with experiment, it's wrong.",
        "author": "Richard Feynman",
        "bio": "Physicist and Nobel laureate",
        "wiki": "https://en.wikipedia.org/wiki/Richard_Feynman",
        "color": 0x3498DB
    },
    {
        "quote": "Measuring programming progress by lines of code is like measuring aircraft building progress by weight.",
        "author": "Bill Gates",
        "bio": "Co-founder of Microsoft",
        "wiki": "https://en.wikipedia.org/wiki/Bill_Gates",
        "color": 0x00A4EF
    },
    {
        "quote": "The Internet is becoming the town square for the global village of tomorrow.",
        "author": "Bill Gates",
        "bio": "Co-founder of Microsoft",
        "wiki": "https://en.wikipedia.org/wiki/Bill_Gates",
        "color": 0x00A4EF
    },
    {
        "quote": "If you can't make it good, at least make it look good.",
        "author": "Bill Gates",
        "bio": "Co-founder of Microsoft",
        "wiki": "https://en.wikipedia.org/wiki/Bill_Gates",
        "color": 0x00A4EF
    },
    {
        "quote": "We always overestimate the change that will occur in the next two years and underestimate the change that will occur in the next ten.",
        "author": "Bill Gates",
        "bio": "Co-founder of Microsoft",
        "wiki": "https://en.wikipedia.org/wiki/Bill_Gates",
        "color": 0x00A4EF
    },
    {
        "quote": "640K ought to be enough for anybody.",
        "author": "Bill Gates",
        "bio": "Co-founder of Microsoft (disputed quote)",
        "wiki": "https://en.wikipedia.org/wiki/Bill_Gates",
        "color": 0x00A4EF
    },
    {
        "quote": "Some people worry that artificial intelligence will make us feel inferior, but then, anybody in his right mind should have an inferiority complex every time he looks at a flower.",
        "author": "Alan Kay",
        "bio": "Computer scientist, pioneer of object-oriented programming",
        "wiki": "https://en.wikipedia.org/wiki/Alan_Kay",
        "color": 0x3498DB
    },
    {
        "quote": "The Internet was done so well that most people think of it as a natural resource like the Pacific Ocean, rather than something that was man-made.",
        "author": "Alan Kay",
        "bio": "Computer scientist, pioneer of object-oriented programming",
        "wiki": "https://en.wikipedia.org/wiki/Alan_Kay",
        "color": 0x3498DB
    },
    {
        "quote": "Don't worry about what anybody else is going to do. The best way to predict the future is to invent it.",
        "author": "Alan Kay",
        "bio": "Computer scientist, pioneer of object-oriented programming",
        "wiki": "https://en.wikipedia.org/wiki/Alan_Kay",
        "color": 0x3498DB
    },
    {
        "quote": "I invented the term 'Object-Oriented', and I can tell you I did not have C++ in mind.",
        "author": "Alan Kay",
        "bio": "Computer scientist, pioneer of object-oriented programming",
        "wiki": "https://en.wikipedia.org/wiki/Alan_Kay",
        "color": 0x3498DB
    },
    {
        "quote": "A change in perspective is worth 80 IQ points.",
        "author": "Alan Kay",
        "bio": "Computer scientist, pioneer of object-oriented programming",
        "wiki": "https://en.wikipedia.org/wiki/Alan_Kay",
        "color": 0x3498DB
    },
    {
        "quote": "Technology is anything that was invented after you were born.",
        "author": "Alan Kay",
        "bio": "Computer scientist, pioneer of object-oriented programming",
        "wiki": "https://en.wikipedia.org/wiki/Alan_Kay",
        "color": 0x3498DB
    },
    {
        "quote": "Artificial intelligence is no match for natural stupidity.",
        "author": "Anonymous",
        "bio": "Tech humor",
        "wiki": None,
        "color": 0xE67E22
    },
    {
        "quote": "There's no place like 127.0.0.1.",
        "author": "Anonymous",
        "bio": "Network humor",
        "wiki": None,
        "color": 0x3498DB
    },
    {
        "quote": "If at first you don't succeed, call it version 1.0.",
        "author": "Anonymous",
        "bio": "Software development humor",
        "wiki": None,
        "color": 0xF39C12
    },
    {
        "quote": "I'm not anti-social; I'm just not user friendly.",
        "author": "Anonymous",
        "bio": "Developer humor",
        "wiki": None,
        "color": 0x95A5A6
    },
    {
        "quote": "Algorithm: Word used by programmers when they don't want to explain what they did.",
        "author": "Anonymous",
        "bio": "Tech humor",
        "wiki": None,
        "color": 0xE67E22
    },
    {
        "quote": "Why do programmers prefer dark mode? Because light attracts bugs!",
        "author": "Anonymous",
        "bio": "Developer humor",
        "wiki": None,
        "color": 0x2C3E50
    },
    {
        "quote": "To iterate is human, to recurse divine.",
        "author": "L. Peter Deutsch",
        "bio": "Computer scientist",
        "wiki": "https://en.wikipedia.org/wiki/L._Peter_Deutsch",
        "color": 0x16A085
    },
    {
        "quote": "Software and cathedrals are much the same – first we build them, then we pray.",
        "author": "Anonymous",
        "bio": "Software engineering wisdom",
        "wiki": None,
        "color": 0x9B59B6
    },
    {
        "quote": "The only truly secure system is one that is powered off, cast in a block of concrete and sealed in a lead-lined room with armed guards.",
        "author": "Gene Spafford",
        "bio": "Computer security expert",
        "wiki": "https://en.wikipedia.org/wiki/Gene_Spafford",
        "color": 0xC0392B
    },
    {
        "quote": "People who tell computers what to do, and people who are told by computers what to do.",
        "author": "Marc Andreessen",
        "bio": "Software engineer and entrepreneur",
        "wiki": "https://en.wikipedia.org/wiki/Marc_Andreessen",
        "color": 0x3498DB
    },
    {
        "quote": "Software is eating the world, but AI is going to eat software.",
        "author": "Jensen Huang",
        "bio": "CEO of NVIDIA",
        "wiki": "https://en.wikipedia.org/wiki/Jensen_Huang",
        "color": 0x76B900  # NVIDIA green
    },
    {
        "quote": "The advance of technology is based on making it fit in so that you don't really even notice it.",
        "author": "Bill Gates",
        "bio": "Co-founder of Microsoft",
        "wiki": "https://en.wikipedia.org/wiki/Bill_Gates",
        "color": 0x00A4EF
    },
    {
        "quote": "Technology is best when it brings people together.",
        "author": "Matt Mullenweg",
        "bio": "Creator of WordPress",
        "wiki": "https://en.wikipedia.org/wiki/Matt_Mullenweg",
        "color": 0x21759B  # WordPress blue
    },
    {
        "quote": "Usage is like oxygen for ideas.",
        "author": "Matt Mullenweg",
        "bio": "Creator of WordPress",
        "wiki": "https://en.wikipedia.org/wiki/Matt_Mullenweg",
        "color": 0x21759B
    },
    {
        "quote": "If you're not embarrassed when you ship your first version, you waited too long.",
        "author": "Matt Mullenweg",
        "bio": "Creator of WordPress",
        "wiki": "https://en.wikipedia.org/wiki/Matt_Mullenweg",
        "color": 0x21759B
    },
    {
        "quote": "The function of good software is to make the complex appear simple.",
        "author": "Grady Booch",
        "bio": "Software engineer, developed UML",
        "wiki": "https://en.wikipedia.org/wiki/Grady_Booch",
        "color": 0x16A085
    },
    {
        "quote": "A system is never finished being developed until it ceases to be used.",
        "author": "Anonymous",
        "bio": "Software lifecycle wisdom",
        "wiki": None,
        "color": 0x95A5A6
    },
    {
        "quote": "The sooner you start to code, the longer the program will take.",
        "author": "Roy Carlson",
        "bio": "Programmer",
        "wiki": None,
        "color": 0xE74C3C
    },
    {
        "quote": "A good programmer is someone who always looks both ways before crossing a one-way street.",
        "author": "Doug Linder",
        "bio": "Software developer",
        "wiki": None,
        "color": 0x3498DB
    },
    {
        "quote": "Software is a great combination between artistry and engineering.",
        "author": "Bill Gates",
        "bio": "Co-founder of Microsoft",
        "wiki": "https://en.wikipedia.org/wiki/Bill_Gates",
        "color": 0x00A4EF
    },
    {
        "quote": "In software, we rarely have meaningful requirements. Even if we do, the only measure of success that matters is whether our solution solves the customer's shifting idea of what their problem is.",
        "author": "Jeff Atwood",
        "bio": "Co-founder of Stack Overflow",
        "wiki": "https://en.wikipedia.org/wiki/Jeff_Atwood",
        "color": 0xF48024
    },
    {
        "quote": "One of the best programming skills you can have is knowing when to walk away for awhile.",
        "author": "Oscar Godson",
        "bio": "Software developer",
        "wiki": None,
        "color": 0x27AE60
    },
    {
        "quote": "Learning to code is learning to create and innovate.",
        "author": "Enda Kenny",
        "bio": "Former Taoiseach of Ireland",
        "wiki": "https://en.wikipedia.org/wiki/Enda_Kenny",
        "color": 0x2ECC71
    },
    {
        "quote": "Everybody in this country should learn to program a computer because it teaches you how to think.",
        "author": "Steve Jobs",
        "bio": "Co-founder of Apple Inc.",
        "wiki": "https://en.wikipedia.org/wiki/Steve_Jobs",
        "color": 0x555555
    },
    {
        "quote": "The computer programmer is a creator of universes for which he alone is responsible. Universes of virtually unlimited complexity can be created in the form of computer programs.",
        "author": "Joseph Weizenbaum",
        "bio": "Computer scientist, creator of ELIZA",
        "wiki": "https://en.wikipedia.org/wiki/Joseph_Weizenbaum",
        "color": 0x9B59B6
    },
    {
        "quote": "Weeks of programming can save you hours of planning.",
        "author": "Anonymous",
        "bio": "Project management wisdom",
        "wiki": None,
        "color": 0xC0392B
    },
    {
        "quote": "It's not a bug – it's an undocumented feature.",
        "author": "Anonymous",
        "bio": "Developer humor",
        "wiki": None,
        "color": 0xF39C12
    },
    {
        "quote": "Before software can be reusable it first has to be usable.",
        "author": "Ralph Johnson",
        "bio": "Computer scientist, Gang of Four author",
        "wiki": "https://en.wikipedia.org/wiki/Ralph_Johnson_(computer_scientist)",
        "color": 0x16A085
    },
    {
        "quote": "It's harder to read code than to write it.",
        "author": "Joel Spolsky",
        "bio": "Co-founder of Stack Overflow",
        "wiki": "https://en.wikipedia.org/wiki/Joel_Spolsky",
        "color": 0xF48024
    },
    {
        "quote": "The best way to get a project done faster is to start sooner.",
        "author": "Jim Highsmith",
        "bio": "Software engineer and author",
        "wiki": None,
        "color": 0x27AE60
    },
    {
        "quote": "Learning to write programs stretches your mind, and helps you think better, creates a way of thinking about things that I think is helpful in all domains.",
        "author": "Bill Gates",
        "bio": "Co-founder of Microsoft",
        "wiki": "https://en.wikipedia.org/wiki/Bill_Gates",
        "color": 0x00A4EF
    },
    {
        "quote": "Give someone a program, you frustrate them for a day; teach them how to program, you frustrate them for a lifetime.",
        "author": "David Leinweber",
        "bio": "Computer scientist",
        "wiki": None,
        "color": 0xE67E22
    },
    {
        "quote": "Simplicity is about subtracting the obvious and adding the meaningful.",
        "author": "John Maeda",
        "bio": "Designer and technologist",
        "wiki": "https://en.wikipedia.org/wiki/John_Maeda",
        "color": 0x9B59B6
    },
    {
        "quote": "The best programmers are not marginally better than merely good ones. They are an order-of-magnitude better.",
        "author": "Randall E. Stross",
        "bio": "Business author",
        "wiki": None,
        "color": 0x2ECC71
    },
    {
        "quote": "The danger from computers is not that they will eventually get as smart as men, but that we will meanwhile agree to meet them halfway.",
        "author": "Bernard Avishai",
        "bio": "Writer and technologist",
        "wiki": None,
        "color": 0xE67E22
    },
    {
        "quote": "Computers are good at following instructions, but not at reading your mind.",
        "author": "Donald Knuth",
        "bio": "Author of 'The Art of Computer Programming'",
        "wiki": "https://en.wikipedia.org/wiki/Donald_Knuth",
        "color": 0x8B4513
    },
    {
        "quote": "The best way to predict the future is to invent it. Really smart people with reasonable funding can do just about anything that doesn't violate too many of Newton's Laws!",
        "author": "Alan Kay",
        "bio": "Computer scientist, pioneer of object-oriented programming",
        "wiki": "https://en.wikipedia.org/wiki/Alan_Kay",
        "color": 0x3498DB
    },
    {
        "quote": "The most important single aspect of software development is to be clear about what you are trying to build.",
        "author": "Bjarne Stroustrup",
        "bio": "Creator of C++",
        "wiki": "https://en.wikipedia.org/wiki/Bjarne_Stroustrup",
        "color": 0x00599C
    },
    {
        "quote": "I don't need to waste my time with a computer just because I am a computer scientist.",
        "author": "Edsger Dijkstra",
        "bio": "Computer scientist and pioneer of structured programming",
        "wiki": "https://en.wikipedia.org/wiki/Edsger_W._Dijkstra",
        "color": 0x34495E
    },
    {
        "quote": "Debugging time increases as a square of the program's size.",
        "author": "Chris Wenham",
        "bio": "Software developer",
        "wiki": None,
        "color": 0xE74C3C
    },
    {
        "quote": "A language that doesn't have everything is actually easier to program in than some that do.",
        "author": "Dennis Ritchie",
        "bio": "Creator of the C programming language",
        "wiki": "https://en.wikipedia.org/wiki/Dennis_Ritchie",
        "color": 0x555555
    },
    {
        "quote": "Obsolete comments are worse than no comments.",
        "author": "Anonymous",
        "bio": "Code documentation wisdom",
        "wiki": None,
        "color": 0xE74C3C
    },
    {
        "quote": "Sometimes the best code is no code at all.",
        "author": "Jeff Atwood",
        "bio": "Co-founder of Stack Overflow",
        "wiki": "https://en.wikipedia.org/wiki/Jeff_Atwood",
        "color": 0xF48024
    },
    {
        "quote": "Every line of code you don't write is one less line to debug, test, and maintain.",
        "author": "Anonymous",
        "bio": "Software minimalism",
        "wiki": None,
        "color": 0x27AE60
    },
    {
        "quote": "Smart data structures and dumb code works a lot better than the other way around.",
        "author": "Eric S. Raymond",
        "bio": "Open source advocate, author of 'The Cathedral and the Bazaar'",
        "wiki": "https://en.wikipedia.org/wiki/Eric_S._Raymond",
        "color": 0xFCC624
    },
    {
        "quote": "Deleted code is debugged code.",
        "author": "Jeff Sickel",
        "bio": "Software developer",
        "wiki": None,
        "color": 0x2ECC71
    },
    {
        "quote": "Less is exponentially more.",
        "author": "Rob Pike",
        "bio": "Computer programmer, co-creator of Go",
        "wiki": "https://en.wikipedia.org/wiki/Rob_Pike",
        "color": 0x00ADD8  # Go blue
    },
    {
        "quote": "Simplicity is complicated.",
        "author": "Rob Pike",
        "bio": "Computer programmer, co-creator of Go",
        "wiki": "https://en.wikipedia.org/wiki/Rob_Pike",
        "color": 0x00ADD8
    },
    {
        "quote": "Systems programmers are the high priests of a low cult.",
        "author": "Robert S. Barton",
        "bio": "Computer architect",
        "wiki": "https://en.wikipedia.org/wiki/Robert_S._Barton",
        "color": 0x34495E
    },
    {
        "quote": "The most important property of a program is whether it accomplishes the intention of its user.",
        "author": "C.A.R. Hoare",
        "bio": "Computer scientist, invented quicksort",
        "wiki": "https://en.wikipedia.org/wiki/Tony_Hoare",
        "color": 0x16A085
    },
    {
        "quote": "Complexity kills. It sucks the life out of developers, it makes products difficult to plan, build, and test.",
        "author": "Ray Ozzie",
        "bio": "Software architect and former Microsoft Chief Software Architect",
        "wiki": "https://en.wikipedia.org/wiki/Ray_Ozzie",
        "color": 0x00A4EF
    },
    {
        "quote": "The trouble with the world is that the stupid are cocksure and the intelligent are full of doubt.",
        "author": "Bertrand Russell",
        "bio": "Philosopher (often applied to programming)",
        "wiki": "https://en.wikipedia.org/wiki/Bertrand_Russell",
        "color": 0x9B59B6
    },
    {
        "quote": "Hofstadter's Law: It always takes longer than you expect, even when you take into account Hofstadter's Law.",
        "author": "Douglas Hofstadter",
        "bio": "Cognitive scientist, author of 'Gödel, Escher, Bach'",
        "wiki": "https://en.wikipedia.org/wiki/Douglas_Hofstadter",
        "color": 0x9B59B6
    },
    {
        "quote": "Computer science education cannot make anybody an expert programmer any more than studying brushes and pigment can make somebody an expert painter.",
        "author": "Eric S. Raymond",
        "bio": "Open source advocate, author of 'The Cathedral and the Bazaar'",
        "wiki": "https://en.wikipedia.org/wiki/Eric_S._Raymond",
        "color": 0xFCC624
    },
    {
        "quote": "The nice thing about standards is that there are so many to choose from.",
        "author": "Andrew S. Tanenbaum",
        "bio": "Computer scientist and professor",
        "wiki": "https://en.wikipedia.org/wiki/Andrew_S._Tanenbaum",
        "color": 0x3498DB
    },
    {
        "quote": "Never trust a computer you can't throw out a window.",
        "author": "Steve Wozniak",
        "bio": "Co-founder of Apple Inc.",
        "wiki": "https://en.wikipedia.org/wiki/Steve_Wozniak",
        "color": 0x555555
    },
    {
        "quote": "If you give someone a program, you will frustrate them for a day; if you teach them how to program, you will frustrate them for a lifetime.",
        "author": "Anonymous",
        "bio": "Programming education humor",
        "wiki": None,
        "color": 0xE67E22
    },
    {
        "quote": "All non-trivial abstractions, to some degree, are leaky.",
        "author": "Joel Spolsky",
        "bio": "Co-founder of Stack Overflow (Law of Leaky Abstractions)",
        "wiki": "https://en.wikipedia.org/wiki/Joel_Spolsky",
        "color": 0xF48024
    },
    {
        "quote": "Measuring software productivity by lines of code is like measuring progress on an airplane by how much it weighs.",
        "author": "Bill Gates",
        "bio": "Co-founder of Microsoft",
        "wiki": "https://en.wikipedia.org/wiki/Bill_Gates",
        "color": 0x00A4EF
    },
    {
        "quote": "We build our computer systems the way we build our cities: over time, without a plan, on top of ruins.",
        "author": "Ellen Ullman",
        "bio": "Computer programmer and author",
        "wiki": "https://en.wikipedia.org/wiki/Ellen_Ullman",
        "color": 0x9B59B6
    },
    {
        "quote": "There are only two hard problems in computer science: cache invalidation and naming things.",
        "author": "Phil Karlton",
        "bio": "Principal programmer at Netscape",
        "wiki": None,
        "color": 0x3498DB
    },
    {
        "quote": "There are 2 hard problems in computer science: cache invalidation, naming things, and off-by-1 errors.",
        "author": "Leon Bambrick",
        "bio": "Software developer (variation on Phil Karlton's quote)",
        "wiki": None,
        "color": 0xE67E22
    },
    {
        "quote": "Java is to JavaScript as car is to carpet.",
        "author": "Chris Heilmann",
        "bio": "Web developer",
        "wiki": None,
        "color": 0xF0DB4F
    },
    {
        "quote": "XML is like violence. If it doesn't solve your problem, you're not using enough of it.",
        "author": "Anonymous",
        "bio": "Developer humor",
        "wiki": None,
        "color": 0xE67E22
    },
    {
        "quote": "The best thing about a boolean is even if you are wrong, you are only off by a bit.",
        "author": "Anonymous",
        "bio": "Programming humor",
        "wiki": None,
        "color": 0x3498DB
    },
    {
        "quote": "Without requirements or design, programming is the art of adding bugs to an empty text file.",
        "author": "Louis Srygley",
        "bio": "Software developer",
        "wiki": None,
        "color": 0xE74C3C
    },
    {
        "quote": "Before you use a framework, make sure you fully understand the problem it's trying to solve.",
        "author": "Anonymous",
        "bio": "Framework wisdom",
        "wiki": None,
        "color": 0x27AE60
    },
    {
        "quote": "The best performance improvement is the transition from the nonworking state to the working state.",
        "author": "John Ousterhout",
        "bio": "Computer scientist, creator of Tcl",
        "wiki": "https://en.wikipedia.org/wiki/John_Ousterhout",
        "color": 0x16A085
    },
    {
        "quote": "A good way to stay flexible is to write less code.",
        "author": "Pragmatic Programmer",
        "bio": "From 'The Pragmatic Programmer'",
        "wiki": None,
        "color": 0x2ECC71
    },
    {
        "quote": "Don't document bad code—rewrite it.",
        "author": "Brian Kernighan",
        "bio": "Co-author of 'The C Programming Language'",
        "wiki": "https://en.wikipedia.org/wiki/Brian_Kernighan",
        "color": 0x555555
    },
    {
        "quote": "No code is faster than no code.",
        "author": "Anonymous",
        "bio": "Performance optimization wisdom",
        "wiki": None,
        "color": 0x27AE60
    },
    {
        "quote": "Perfection is achieved, not when there is nothing more to add, but when there is nothing left to take away.",
        "author": "Antoine de Saint-Exupéry",
        "bio": "Author (often applied to software design)",
        "wiki": "https://en.wikipedia.org/wiki/Antoine_de_Saint-Exup%C3%A9ry",
        "color": 0x9B59B6
    },
    {
        "quote": "The best code is no code at all.",
        "author": "Jeff Atwood",
        "bio": "Co-founder of Stack Overflow",
        "wiki": "https://en.wikipedia.org/wiki/Jeff_Atwood",
        "color": 0xF48024
    },
    {
        "quote": "Write code that is easy to delete, not easy to extend.",
        "author": "Tef",
        "bio": "Programmer",
        "wiki": None,
        "color": 0x3498DB
    },
    {
        "quote": "Programming can be fun, so can cryptography; however they should not be combined.",
        "author": "Kreitzberg & Shneiderman",
        "bio": "Computer scientists",
        "wiki": None,
        "color": 0xE67E22
    },
    {
        "quote": "Copy-and-paste is a design error.",
        "author": "David Parnas",
        "bio": "Computer scientist",
        "wiki": "https://en.wikipedia.org/wiki/David_Parnas",
        "color": 0xE74C3C
    },
    {
        "quote": "Code is read much more often than it is written.",
        "author": "Guido van Rossum",
        "bio": "Creator of Python",
        "wiki": "https://en.wikipedia.org/wiki/Guido_van_Rossum",
        "color": 0x3776AB
    },
    {
        "quote": "Now is better than never.",
        "author": "Guido van Rossum",
        "bio": "Creator of Python (from The Zen of Python)",
        "wiki": "https://en.wikipedia.org/wiki/Guido_van_Rossum",
        "color": 0x3776AB
    },
    {
        "quote": "If the implementation is hard to explain, it's a bad idea.",
        "author": "Guido van Rossum",
        "bio": "Creator of Python (from The Zen of Python)",
        "wiki": "https://en.wikipedia.org/wiki/Guido_van_Rossum",
        "color": 0x3776AB
    },
    {
        "quote": "Python is an experiment in how much freedom programmers need. Too much freedom and nobody can read another's code; too little and expressiveness is endangered.",
        "author": "Guido van Rossum",
        "bio": "Creator of Python",
        "wiki": "https://en.wikipedia.org/wiki/Guido_van_rossum",
        "color": 0x3776AB
    },
    {
        "quote": "I'm a very lazy person who likes to get credit for things other people actually do.",
        "author": "Linus Torvalds",
        "bio": "Creator of Linux and Git",
        "wiki": "https://en.wikipedia.org/wiki/Linus_Torvalds",
        "color": 0xFCC624
    },
    {
        "quote": "In real open source, you have the right to control your own destiny.",
        "author": "Linus Torvalds",
        "bio": "Creator of Linux and Git",
        "wiki": "https://en.wikipedia.org/wiki/Linus_Torvalds",
        "color": 0xFCC624
    },
    {
        "quote": "Microsoft isn't evil, they just make really crappy operating systems.",
        "author": "Linus Torvalds",
        "bio": "Creator of Linux and Git",
        "wiki": "https://en.wikipedia.org/wiki/Linus_Torvalds",
        "color": 0xFCC624
    },
    {
        "quote": "See, you not only have to be a good coder to create a system like Linux, you have to be a sneaky bastard too.",
        "author": "Linus Torvalds",
        "bio": "Creator of Linux and Git",
        "wiki": "https://en.wikipedia.org/wiki/Linus_Torvalds",
        "color": 0xFCC624
    },
    {
        "quote": "The Linux philosophy is 'Laugh in the face of danger'. Oops. Wrong One. 'Do it yourself'. Yes, that's it.",
        "author": "Linus Torvalds",
        "bio": "Creator of Linux and Git",
        "wiki": "https://en.wikipedia.org/wiki/Linus_Torvalds",
        "color": 0xFCC624
    },
    {
        "quote": "In many cases, the user interface to a program is the most important part for a commercial company: whether the programs works correctly or not seems to be secondary.",
        "author": "Linus Torvalds",
        "bio": "Creator of Linux and Git",
        "wiki": "https://en.wikipedia.org/wiki/Linus_Torvalds",
        "color": 0xFCC624
    },
    {
        "quote": "My name is Linus, and I am your God.",
        "author": "Linus Torvalds",
        "bio": "Creator of Linux and Git",
        "wiki": "https://en.wikipedia.org/wiki/Linus_Torvalds",
        "color": 0xFCC624
    },
    {
        "quote": "We're not talking about DOS. We're talking about Windows, which is a completely different beast.",
        "author": "Linus Torvalds",
        "bio": "Creator of Linux and Git",
        "wiki": "https://en.wikipedia.org/wiki/Linus_Torvalds",
        "color": 0xFCC624
    },
    {
        "quote": "Portability is for people who cannot write new programs.",
        "author": "Linus Torvalds",
        "bio": "Creator of Linux and Git",
        "wiki": "https://en.wikipedia.org/wiki/Linus_Torvalds",
        "color": 0xFCC624
    },
    {
        "quote": "Some people have told me they don't think a fat penguin really embodies the grace of Linux, which just tells me they have never seen an angry penguin charging at them in excess of 100mph.",
        "author": "Linus Torvalds",
        "bio": "Creator of Linux and Git",
        "wiki": "https://en.wikipedia.org/wiki/Linus_Torvalds",
        "color": 0xFCC624
    },
    {
        "quote": "Eventually the revolutionaries become the established culture, and then what will they do?",
        "author": "Linus Torvalds",
        "bio": "Creator of Linux and Git",
        "wiki": "https://en.wikipedia.org/wiki/Linus_Torvalds",
        "color": 0xFCC624
    },
    {
        "quote": "Once you realize that documentation should be laughed at, peed upon, put on fire, and just ridiculed in general, then, and only then, have you reached the level where you can safely read it and try to use it to actually implement a driver.",
        "author": "Linus Torvalds",
        "bio": "Creator of Linux and Git",
        "wiki": "https://en.wikipedia.org/wiki/Linus_Torvalds",
        "color": 0xFCC624
    },
    {
        "quote": "I've actually found the image of Silicon Valley as a hotbed of money-grubbing tech people to be pretty false, but maybe that's because the people I hang out with are all really engineers.",
        "author": "Linus Torvalds",
        "bio": "Creator of Linux and Git",
        "wiki": "https://en.wikipedia.org/wiki/Linus_Torvalds",
        "color": 0xFCC624
    },
    {
        "quote": "In open source, we feel strongly that to really do something well, you have to get a lot of people involved.",
        "author": "Linus Torvalds",
        "bio": "Creator of Linux and Git",
        "wiki": "https://en.wikipedia.org/wiki/Linus_Torvalds",
        "color": 0xFCC624
    },
    {
        "quote": "Software is like sex: It's better when it's free.",
        "author": "Linus Torvalds",
        "bio": "Creator of Linux and Git",
        "wiki": "https://en.wikipedia.org/wiki/Linus_Torvalds",
        "color": 0xFCC624
    },
    {
        "quote": "The memory management on the PowerPC can be used to frighten small children.",
        "author": "Linus Torvalds",
        "bio": "Creator of Linux and Git",
        "wiki": "https://en.wikipedia.org/wiki/Linus_Torvalds",
        "color": 0xFCC624
    },
    {
        "quote": "Talk is cheap. Show me the code.",
        "author": "Linus Torvalds",
        "bio": "Creator of Linux and Git",
        "wiki": "https://en.wikipedia.org/wiki/Linus_Torvalds",
        "color": 0xFCC624
    },
    {
        "quote": "I'm basically a very lazy person who likes to take credit for things other people actually do.",
        "author": "Linus Torvalds",
        "bio": "Creator of Linux and Git",
        "wiki": "https://en.wikipedia.org/wiki/Linus_Torvalds",
        "color": 0xFCC624
    },
    {
        "quote": "Non-free software is a waste of company resources, public resources, personal resources.",
        "author": "Richard Stallman",
        "bio": "Founder of GNU Project and Free Software Foundation",
        "wiki": "https://en.wikipedia.org/wiki/Richard_Stallman",
        "color": 0xA42E2B
    },
    {
        "quote": "Proprietary software is an injustice.",
        "author": "Richard Stallman",
        "bio": "Founder of GNU Project and Free Software Foundation",
        "wiki": "https://en.wikipedia.org/wiki/Richard_Stallman",
        "color": 0xA42E2B
    },
    {
        "quote": "I could have made money this way, and perhaps amused myself writing code. But I knew that at the end of my career, I would look back on years of building walls to divide people, and feel I had spent my life making the world a worse place.",
        "author": "Richard Stallman",
        "bio": "Founder of GNU Project and Free Software Foundation",
        "wiki": "https://en.wikipedia.org/wiki/Richard_Stallman",
        "color": 0xA42E2B
    },
    {
        "quote": "Sharing is good, and with digital technology, sharing is easy.",
        "author": "Richard Stallman",
        "bio": "Founder of GNU Project and Free Software Foundation",
        "wiki": "https://en.wikipedia.org/wiki/Richard_Stallman",
        "color": 0xA42E2B
    },
    {
        "quote": "Value your freedom or you will lose it, teaches history. 'Don't bother us with politics,' respond those who don't want to learn.",
        "author": "Richard Stallman",
        "bio": "Founder of GNU Project and Free Software Foundation",
        "wiki": "https://en.wikipedia.org/wiki/Richard_Stallman",
        "color": 0xA42E2B
    },
    {
        "quote": "I suppose many people will continue moving towards careless computing, because there's a sucker born every minute.",
        "author": "Richard Stallman",
        "bio": "Founder of GNU Project and Free Software Foundation",
        "wiki": "https://en.wikipedia.org/wiki/Richard_Stallman",
        "color": 0xA42E2B
    },
    {
        "quote": "Android is very different from the GNU/Linux operating system because it contains very little of GNU. Indeed, just about the only component in common between Android and GNU/Linux is Linux, the kernel.",
        "author": "Richard Stallman",
        "bio": "Founder of GNU Project and Free Software Foundation",
        "wiki": "https://en.wikipedia.org/wiki/Richard_Stallman",
        "color": 0xA42E2B
    },
    {
        "quote": "The paradigm of competition is a race: by rewarding the winner, we encourage everyone to run faster. When capitalism really works this way, it does a good job; but its defenders are wrong in assuming it always works this way.",
        "author": "Richard Stallman",
        "bio": "Founder of GNU Project and Free Software Foundation",
        "wiki": "https://en.wikipedia.org/wiki/Richard_Stallman",
        "color": 0xA42E2B
    },
    {
        "quote": "If you want to accomplish something in the world, idealism is not enough - you need to choose a method that works to achieve the goal.",
        "author": "Richard Stallman",
        "bio": "Founder of GNU Project and Free Software Foundation",
        "wiki": "https://en.wikipedia.org/wiki/Richard_Stallman",
        "color": 0xA42E2B
    },
    {
        "quote": "Sharing knowledge is the most fundamental act of friendship. Because it is a way you can give something without losing something.",
        "author": "Richard Stallman",
        "bio": "Founder of GNU Project and Free Software Foundation",
        "wiki": "https://en.wikipedia.org/wiki/Richard_Stallman",
        "color": 0xA42E2B
    },
    {
        "quote": "C++ is a horrible language. It's made more horrible by the fact that a lot of substandard programmers use it.",
        "author": "Linus Torvalds",
        "bio": "Creator of Linux and Git",
        "wiki": "https://en.wikipedia.org/wiki/Linus_Torvalds",
        "color": 0xFCC624
    },
    {
        "quote": "Controlling a laser with Linux is crazy, but everyone in this room is crazy in his own way. So if you want to use Linux to control an industrial welding laser, I have no problem with your using PREEMPT_RT.",
        "author": "Linus Torvalds",
        "bio": "Creator of Linux and Git",
        "wiki": "https://en.wikipedia.org/wiki/Linus_Torvalds",
        "color": 0xFCC624
    },
    {
        "quote": "Security people are often the black-and-white kind of people that I can't stand. I think the OpenBSD crowd is a bunch of masturbating monkeys.",
        "author": "Linus Torvalds",
        "bio": "Creator of Linux and Git",
        "wiki": "https://en.wikipedia.org/wiki/Linus_Torvalds",
        "color": 0xFCC624
    },
    {
        "quote": "Only wimps use tape backup. Real men just upload their important stuff on ftp and let the rest of the world mirror it.",
        "author": "Linus Torvalds",
        "bio": "Creator of Linux and Git",
        "wiki": "https://en.wikipedia.org/wiki/Linus_Torvalds",
        "color": 0xFCC624
    },
    {
        "quote": "The obvious mathematical breakthrough would be development of an easy way to factor large prime numbers.",
        "author": "Bill Gates",
        "bio": "Co-founder of Microsoft",
        "wiki": "https://en.wikipedia.org/wiki/Bill_Gates",
        "color": 0x00A4EF
    },
    {
        "quote": "The future is already here — it's just not very evenly distributed.",
        "author": "William Gibson",
        "bio": "Science fiction author",
        "wiki": "https://en.wikipedia.org/wiki/William_Gibson",
        "color": 0x9B59B6
    },
    {
        "quote": "The street finds its own uses for things.",
        "author": "William Gibson",
        "bio": "Science fiction author",
        "wiki": "https://en.wikipedia.org/wiki/William_Gibson",
        "color": 0x9B59B6
    },
    {
        "quote": "Cyberspace. A consensual hallucination.",
        "author": "William Gibson",
        "bio": "Science fiction author",
        "wiki": "https://en.wikipedia.org/wiki/William_Gibson",
        "color": 0x9B59B6
    },
    {
        "quote": "We are stuck with technology when what we really want is just stuff that works.",
        "author": "Douglas Adams",
        "bio": "Author of 'The Hitchhiker's Guide to the Galaxy'",
        "wiki": "https://en.wikipedia.org/wiki/Douglas_Adams",
        "color": 0xE67E22
    },
    {
        "quote": "I've come up with a set of rules that describe our reactions to technologies: 1. Anything that is in the world when you're born is normal and ordinary. 2. Anything invented between when you're 15 and 35 is new and exciting. 3. Anything invented after you're 35 is against the natural order of things.",
        "author": "Douglas Adams",
        "bio": "Author of 'The Hitchhiker's Guide to the Galaxy'",
        "wiki": "https://en.wikipedia.org/wiki/Douglas_Adams",
        "color": 0xE67E22
    },
    {
        "quote": "A common mistake that people make when trying to design something completely foolproof is to underestimate the ingenuity of complete fools.",
        "author": "Douglas Adams",
        "bio": "Author of 'The Hitchhiker's Guide to the Galaxy'",
        "wiki": "https://en.wikipedia.org/wiki/Douglas_Adams",
        "color": 0xE67E22
    },
    {
        "quote": "Technology is a word that describes something that doesn't work yet.",
        "author": "Douglas Adams",
        "bio": "Author of 'The Hitchhiker's Guide to the Galaxy'",
        "wiki": "https://en.wikipedia.org/wiki/Douglas_Adams",
        "color": 0xE67E22
    },
    {
        "quote": "Humans are allergic to change. They love to say, 'We've always done it this way.' I try to fight that. That's why I have a clock on my wall that runs counter-clockwise.",
        "author": "Grace Hopper",
        "bio": "Computer science pioneer, inventor of first compiler",
        "wiki": "https://en.wikipedia.org/wiki/Grace_Hopper",
        "color": 0xE91E63
    },
    {
        "quote": "A ship in a harbor is safe, but that's not what ships are built for.",
        "author": "Grace Hopper",
        "bio": "Computer science pioneer, inventor of first compiler",
        "wiki": "https://en.wikipedia.org/wiki/Grace_Hopper",
        "color": 0xE91E63
    },
    {
        "quote": "If it's a good idea, go ahead and do it. It is much easier to apologize than it is to get permission.",
        "author": "Grace Hopper",
        "bio": "Computer science pioneer, inventor of first compiler",
        "wiki": "https://en.wikipedia.org/wiki/Grace_Hopper",
        "color": 0xE91E63
    },
    {
        "quote": "The most dangerous phrase in the language is, 'We've always done it this way.'",
        "author": "Grace Hopper",
        "bio": "Computer science pioneer, inventor of first compiler",
        "wiki": "https://en.wikipedia.org/wiki/Grace_Hopper",
        "color": 0xE91E63
    },
    {
        "quote": "Innovation is the ability to see change as an opportunity - not a threat.",
        "author": "Steve Jobs",
        "bio": "Co-founder of Apple Inc.",
        "wiki": "https://en.wikipedia.org/wiki/Steve_Jobs",
        "color": 0x555555
    },
    {
        "quote": "You can't connect the dots looking forward; you can only connect them looking backwards.",
        "author": "Steve Jobs",
        "bio": "Co-founder of Apple Inc.",
        "wiki": "https://en.wikipedia.org/wiki/Steve_Jobs",
        "color": 0x555555
    },
    {
        "quote": "The people who are crazy enough to think they can change the world are the ones who do.",
        "author": "Steve Jobs",
        "bio": "Co-founder of Apple Inc.",
        "wiki": "https://en.wikipedia.org/wiki/Steve_Jobs",
        "color": 0x555555
    },
    {
        "quote": "Have the courage to follow your heart and intuition. They somehow already know what you truly want to become.",
        "author": "Steve Jobs",
        "bio": "Co-founder of Apple Inc.",
        "wiki": "https://en.wikipedia.org/wiki/Steve_Jobs",
        "color": 0x555555
    },
    {
        "quote": "Remembering that you are going to die is the best way I know to avoid the trap of thinking you have something to lose.",
        "author": "Steve Jobs",
        "bio": "Co-founder of Apple Inc.",
        "wiki": "https://en.wikipedia.org/wiki/Steve_Jobs",
        "color": 0x555555
    },
    {
        "quote": "Your time is limited, don't waste it living someone else's life.",
        "author": "Steve Jobs",
        "bio": "Co-founder of Apple Inc.",
        "wiki": "https://en.wikipedia.org/wiki/Steve_Jobs",
        "color": 0x555555
    },
    {
        "quote": "Sometimes life hits you in the head with a brick. Don't lose faith.",
        "author": "Steve Jobs",
        "bio": "Co-founder of Apple Inc.",
        "wiki": "https://en.wikipedia.org/wiki/Steve_Jobs",
        "color": 0x555555
    },
    {
        "quote": "I think if you do something and it turns out pretty good, then you should go do something else wonderful, not dwell on it for too long.",
        "author": "Steve Jobs",
        "bio": "Co-founder of Apple Inc.",
        "wiki": "https://en.wikipedia.org/wiki/Steve_Jobs",
        "color": 0x555555
    },
    {
        "quote": "Getting fired from Apple was the best thing that could have ever happened to me. The heaviness of being successful was replaced by the lightness of being a beginner again.",
        "author": "Steve Jobs",
        "bio": "Co-founder of Apple Inc.",
        "wiki": "https://en.wikipedia.org/wiki/Steve_Jobs",
        "color": 0x555555
    },
    {
        "quote": "Be a yardstick of quality. Some people aren't used to an environment where excellence is expected.",
        "author": "Steve Jobs",
        "bio": "Co-founder of Apple Inc.",
        "wiki": "https://en.wikipedia.org/wiki/Steve_Jobs",
        "color": 0x555555
    },
    {
        "quote": "Details matter, it's worth waiting to get it right.",
        "author": "Steve Jobs",
        "bio": "Co-founder of Apple Inc.",
        "wiki": "https://en.wikipedia.org/wiki/Steve_Jobs",
        "color": 0x555555
    },
    {
        "quote": "Don't let the noise of others' opinions drown out your own inner voice.",
        "author": "Steve Jobs",
        "bio": "Co-founder of Apple Inc.",
        "wiki": "https://en.wikipedia.org/wiki/Steve_Jobs",
        "color": 0x555555
    },
    {
        "quote": "My model for business is The Beatles. They were four guys who kept each other's kind of negative tendencies in check.",
        "author": "Steve Jobs",
        "bio": "Co-founder of Apple Inc.",
        "wiki": "https://en.wikipedia.org/wiki/Steve_Jobs",
        "color": 0x555555
    },
    {
        "quote": "I want to put a ding in the universe.",
        "author": "Steve Jobs",
        "bio": "Co-founder of Apple Inc.",
        "wiki": "https://en.wikipedia.org/wiki/Steve_Jobs",
        "color": 0x555555
    },
    {
        "quote": "If you define the problem correctly, you almost have the solution.",
        "author": "Steve Jobs",
        "bio": "Co-founder of Apple Inc.",
        "wiki": "https://en.wikipedia.org/wiki/Steve_Jobs",
        "color": 0x555555
    },
    {
        "quote": "Great things in business are never done by one person. They're done by a team of people.",
        "author": "Steve Jobs",
        "bio": "Co-founder of Apple Inc.",
        "wiki": "https://en.wikipedia.org/wiki/Steve_Jobs",
        "color": 0x555555
    },
    {
        "quote": "I'm convinced that about half of what separates the successful entrepreneurs from the non-successful ones is pure perseverance.",
        "author": "Steve Jobs",
        "bio": "Co-founder of Apple Inc.",
        "wiki": "https://en.wikipedia.org/wiki/Steve_Jobs",
        "color": 0x555555
    },
    {
        "quote": "We're here to put a dent in the universe. Otherwise why else even be here?",
        "author": "Steve Jobs",
        "bio": "Co-founder of Apple Inc.",
        "wiki": "https://en.wikipedia.org/wiki/Steve_Jobs",
        "color": 0x555555
    },
    {
        "quote": "My favorite things in life don't cost any money. It's really clear that the most precious resource we all have is time.",
        "author": "Steve Jobs",
        "bio": "Co-founder of Apple Inc.",
        "wiki": "https://en.wikipedia.org/wiki/Steve_Jobs",
        "color": 0x555555
    },
    {
        "quote": "Technology is nothing. What's important is that you have a faith in people, that they're basically good and smart, and if you give them tools, they'll do wonderful things with them.",
        "author": "Steve Jobs",
        "bio": "Co-founder of Apple Inc.",
        "wiki": "https://en.wikipedia.org/wiki/Steve_Jobs",
        "color": 0x555555
    },
    {
        "quote": "Computers themselves, and software yet to be developed, will revolutionize the way we learn.",
        "author": "Steve Jobs",
        "bio": "Co-founder of Apple Inc.",
        "wiki": "https://en.wikipedia.org/wiki/Steve_Jobs",
        "color": 0x555555
    },
    {
        "quote": "The only way to do great work is to love what you do.",
        "author": "Steve Jobs",
        "bio": "Co-founder of Apple Inc.",
        "wiki": "https://en.wikipedia.org/wiki/Steve_Jobs",
        "color": 0x555555
    },
    {
        "quote": "You need to have a collaborative hiring process.",
        "author": "Steve Jobs",
        "bio": "Co-founder of Apple Inc.",
        "wiki": "https://en.wikipedia.org/wiki/Steve_Jobs",
        "color": 0x555555
    },
    {
        "quote": "What is Apple, after all? Apple is about people who think 'outside the box,' people who want to use computers to help them change the world.",
        "author": "Steve Jobs",
        "bio": "Co-founder of Apple Inc.",
        "wiki": "https://en.wikipedia.org/wiki/Steve_Jobs",
        "color": 0x555555
    },
    {
        "quote": "Let's go invent tomorrow instead of worrying about what happened yesterday.",
        "author": "Steve Jobs",
        "bio": "Co-founder of Apple Inc.",
        "wiki": "https://en.wikipedia.org/wiki/Steve_Jobs",
        "color": 0x555555
    },
    {
        "quote": "You can't just ask customers what they want and then try to give that to them. By the time you get it built, they'll want something new.",
        "author": "Steve Jobs",
        "bio": "Co-founder of Apple Inc.",
        "wiki": "https://en.wikipedia.org/wiki/Steve_Jobs",
        "color": 0x555555
    },
    {
        "quote": "The greatest artists like Dylan, Picasso and Newton risked failure. And if we want to be great, we've got to risk it too.",
        "author": "Steve Jobs",
        "bio": "Co-founder of Apple Inc.",
        "wiki": "https://en.wikipedia.org/wiki/Steve_Jobs",
        "color": 0x555555
    },
    {
        "quote": "We don't get a chance to do that many things, and everyone should be really excellent. Because this is our life.",
        "author": "Steve Jobs",
        "bio": "Co-founder of Apple Inc.",
        "wiki": "https://en.wikipedia.org/wiki/Steve_Jobs",
        "color": 0x555555
    },
    {
        "quote": "The broader one's understanding of the human experience, the better design we will have.",
        "author": "Steve Jobs",
        "bio": "Co-founder of Apple Inc.",
        "wiki": "https://en.wikipedia.org/wiki/Steve_Jobs",
        "color": 0x555555
    },
    {
        "quote": "For the past 33 years, I have looked in the mirror every morning and asked myself: 'If today were the last day of my life, would I want to do what I am about to do today?'",
        "author": "Steve Jobs",
        "bio": "Co-founder of Apple Inc.",
        "wiki": "https://en.wikipedia.org/wiki/Steve_Jobs",
        "color": 0x555555
    },
    {
        "quote": "I think we're having fun. I think our customers really like our products. And we're always trying to do better.",
        "author": "Steve Jobs",
        "bio": "Co-founder of Apple Inc.",
        "wiki": "https://en.wikipedia.org/wiki/Steve_Jobs",
        "color": 0x555555
    },
    {
        "quote": "Why join the navy if you can be a pirate?",
        "author": "Steve Jobs",
        "bio": "Co-founder of Apple Inc.",
        "wiki": "https://en.wikipedia.org/wiki/Steve_Jobs",
        "color": 0x555555
    },
    {
        "quote": "I would trade all of my technology for an afternoon with Socrates.",
        "author": "Steve Jobs",
        "bio": "Co-founder of Apple Inc.",
        "wiki": "https://en.wikipedia.org/wiki/Steve_Jobs",
        "color": 0x555555
    },
    {
        "quote": "When you're a carpenter making a beautiful chest of drawers, you're not going to use a piece of plywood on the back.",
        "author": "Steve Jobs",
        "bio": "Co-founder of Apple Inc.",
        "wiki": "https://en.wikipedia.org/wiki/Steve_Jobs",
        "color": 0x555555
    },
    {
        "quote": "Bottom line is, I didn't return to Apple to make a fortune. I've been very lucky in my life and already have one.",
        "author": "Steve Jobs",
        "bio": "Co-founder of Apple Inc.",
        "wiki": "https://en.wikipedia.org/wiki/Steve_Jobs",
        "color": 0x555555
    },
    {
        "quote": "The question of whether computers can think is like the question of whether submarines can swim.",
        "author": "Edsger Dijkstra",
        "bio": "Computer scientist and pioneer of structured programming",
        "wiki": "https://en.wikipedia.org/wiki/Edsger_W._Dijkstra",
        "color": 0x34495E
    },
    {
        "quote": "If we want users to like our software, we should design it to behave like a likeable person.",
        "author": "Alan Cooper",
        "bio": "Software designer and programmer, 'Father of Visual Basic'",
        "wiki": "https://en.wikipedia.org/wiki/Alan_Cooper",
        "color": 0x3498DB
    },
    {
        "quote": "No matter how cool your interface is, it would be better if there were less of it.",
        "author": "Alan Cooper",
        "bio": "Software designer and programmer, 'Father of Visual Basic'",
        "wiki": "https://en.wikipedia.org/wiki/Alan_Cooper",
        "color": 0x3498DB
    },
    {
        "quote": "If you think good architecture is expensive, try bad architecture.",
        "author": "Brian Foote",
        "bio": "Software architect",
        "wiki": None,
        "color": 0xE74C3C
    },
    {
        "quote": "A primary cause of complexity is that software vendors uncritically adopt almost any feature that users want.",
        "author": "Niklaus Wirth",
        "bio": "Computer scientist, creator of Pascal",
        "wiki": "https://en.wikipedia.org/wiki/Niklaus_Wirth",
        "color": 0x2E7D32
    },
    {
        "quote": "The greatest single programming language ever designed.",
        "author": "Alan Kay",
        "bio": "Computer scientist (speaking about Lisp)",
        "wiki": "https://en.wikipedia.org/wiki/Alan_Kay",
        "color": 0x3498DB
    },
    {
        "quote": "Any sufficiently advanced technology is indistinguishable from magic.",
        "author": "Arthur C. Clarke",
        "bio": "Science fiction author (Clarke's Third Law)",
        "wiki": "https://en.wikipedia.org/wiki/Arthur_C._Clarke",
        "color": 0x9B59B6
    },
    {
        "quote": "Any sufficiently advanced bug is indistinguishable from a feature.",
        "author": "Rich Kulawiec",
        "bio": "Tech community (variation on Clarke's Third Law)",
        "wiki": None,
        "color": 0xE67E22
    },
    {
        "quote": "The function of good software is to make the complex appear to be simple.",
        "author": "Grady Booch",
        "bio": "Software engineer, developed UML",
        "wiki": "https://en.wikipedia.org/wiki/Grady_Booch",
        "color": 0x16A085
    },
    {
        "quote": "Don't worry if it doesn't work right. If everything did, you'd be out of a job.",
        "author": "Mosher's Law of Software Engineering",
        "bio": "Software engineering wisdom",
        "wiki": None,
        "color": 0xE67E22
    },
    {
        "quote": "The first 90 percent of the code accounts for the first 90 percent of the development time. The remaining 10 percent of the code accounts for the other 90 percent of the development time.",
        "author": "Tom Cargill",
        "bio": "Software engineer (Ninety-ninety rule)",
        "wiki": None,
        "color": 0xE74C3C
    },
    {
        "quote": "In theory, theory and practice are the same. In practice, they are not.",
        "author": "Albert Einstein",
        "bio": "Theoretical physicist (attributed)",
        "wiki": "https://en.wikipedia.org/wiki/Albert_Einstein",
        "color": 0x34495E
    },
    {
        "quote": "There are only two industries that call their customers 'users': illegal drugs and software.",
        "author": "Edward Tufte",
        "bio": "Statistician and data visualization pioneer",
        "wiki": "https://en.wikipedia.org/wiki/Edward_Tufte",
        "color": 0xE67E22
    },
    {
        "quote": "I have always wished for my computer to be as easy to use as my telephone; my wish has come true because I can no longer figure out how to use my telephone.",
        "author": "Bjarne Stroustrup",
        "bio": "Creator of C++",
        "wiki": "https://en.wikipedia.org/wiki/Bjarne_Stroustrup",
        "color": 0x00599C
    },
    {
        "quote": "Fancy algorithms are slow when n is small, and n is usually small.",
        "author": "Rob Pike",
        "bio": "Computer programmer, co-creator of Go",
        "wiki": "https://en.wikipedia.org/wiki/Rob_Pike",
        "color": 0x00ADD8
    },
    {
        "quote": "Data dominates. If you've chosen the right data structures and organized things well, the algorithms will almost always be self-evident.",
        "author": "Rob Pike",
        "bio": "Computer programmer, co-creator of Go",
        "wiki": "https://en.wikipedia.org/wiki/Rob_Pike",
        "color": 0x00ADD8
    },
    {
        "quote": "A little copying is better than a little dependency.",
        "author": "Rob Pike",
        "bio": "Computer programmer, co-creator of Go",
        "wiki": "https://en.wikipedia.org/wiki/Rob_Pike",
        "color": 0x00ADD8
    },
    {
        "quote": "Caches are bugs waiting to happen.",
        "author": "Rob Pike",
        "bio": "Computer programmer, co-creator of Go",
        "wiki": "https://en.wikipedia.org/wiki/Rob_Pike",
        "color": 0x00ADD8
    },
    {
        "quote": "Interfaces are more important than implementations.",
        "author": "Rob Pike",
        "bio": "Computer programmer, co-creator of Go",
        "wiki": "https://en.wikipedia.org/wiki/Rob_Pike",
        "color": 0x00ADD8
    },
    {
        "quote": "Don't panic.",
        "author": "Rob Pike",
        "bio": "Computer programmer, co-creator of Go",
        "wiki": "https://en.wikipedia.org/wiki/Rob_Pike",
        "color": 0x00ADD8
    },
    {
        "quote": "Every program attempts to expand until it can read mail. Those programs which cannot so expand are replaced by ones which can.",
        "author": "Jamie Zawinski",
        "bio": "Programmer and DNA Lounge owner (Zawinski's Law)",
        "wiki": "https://en.wikipedia.org/wiki/Jamie_Zawinski",
        "color": 0xE67E22
    },
    {
        "quote": "Some people, when confronted with a problem, think 'I know, I'll use regular expressions.' Now they have two problems.",
        "author": "Jamie Zawinski",
        "bio": "Programmer and DNA Lounge owner",
        "wiki": "https://en.wikipedia.org/wiki/Jamie_Zawinski",
        "color": 0xE67E22
    },
    {
        "quote": "Linux is only free if your time has no value.",
        "author": "Jamie Zawinski",
        "bio": "Programmer and DNA Lounge owner",
        "wiki": "https://en.wikipedia.org/wiki/Jamie_Zawinski",
        "color": 0xE67E22
    },
    {
        "quote": "Your mail client is a web browser now.",
        "author": "Jamie Zawinski",
        "bio": "Programmer and DNA Lounge owner",
        "wiki": "https://en.wikipedia.org/wiki/Jamie_Zawinski",
        "color": 0xE67E22
    },
    {
        "quote": "Every program is a part of some other program and rarely fits.",
        "author": "Alan J. Perlis",
        "bio": "First recipient of the Turing Award",
        "wiki": "https://en.wikipedia.org/wiki/Alan_Perlis",
        "color": 0x16A085
    },
    {
        "quote": "If a program manipulates a large amount of data, it does so in a small number of ways.",
        "author": "Alan J. Perlis",
        "bio": "First recipient of the Turing Award",
        "wiki": "https://en.wikipedia.org/wiki/Alan_Perlis",
        "color": 0x16A085
    },
    {
        "quote": "Symmetry is a complexity-reducing concept; seek it everywhere.",
        "author": "Alan J. Perlis",
        "bio": "First recipient of the Turing Award",
        "wiki": "https://en.wikipedia.org/wiki/Alan_Perlis",
        "color": 0x16A085
    },
    {
        "quote": "It is better to have 100 functions operate on one data structure than 10 functions on 10 data structures.",
        "author": "Alan J. Perlis",
        "bio": "First recipient of the Turing Award",
        "wiki": "https://en.wikipedia.org/wiki/Alan_Perlis",
        "color": 0x16A085
    },
    {
        "quote": "Get into a rut early: Do the same processes the same way. Accumulate idioms. Standardize.",
        "author": "Alan J. Perlis",
        "bio": "First recipient of the Turing Award",
        "wiki": "https://en.wikipedia.org/wiki/Alan_Perlis",
        "color": 0x16A085
    },
    {
        "quote": "There is nothing wrong with a program that crashes every day so long as it works properly before it crashes.",
        "author": "Chris Chedgey",
        "bio": "Software engineer",
        "wiki": None,
        "color": 0xE67E22
    },
    {
        "quote": "Writing code has a place in the human hierarchy worth more than clear art and less than somewhat dirty sex.",
        "author": "Freek Zandbergen",
        "bio": "Developer",
        "wiki": None,
        "color": 0x9B59B6
    },
    {
        "quote": "Programming is breaking one big impossible task into several small possible tasks.",
        "author": "Jazzwant",
        "bio": "Developer",
        "wiki": None,
        "color": 0x27AE60
    },
    {
        "quote": "A user interface is like a joke. If you have to explain it, it's not that good.",
        "author": "Martin LeBlanc",
        "bio": "Designer",
        "wiki": None,
        "color": 0x3498DB
    },
    {
        "quote": "The best programmers are not just good at coding but good at managing complexity.",
        "author": "Steve McConnell",
        "bio": "Author of 'Code Complete'",
        "wiki": "https://en.wikipedia.org/wiki/Steve_McConnell",
        "color": 0x2ECC71
    },
    {
        "quote": "The cardinal sin in programming is premature optimization.",
        "author": "Michael A. Jackson",
        "bio": "Computer scientist",
        "wiki": "https://en.wikipedia.org/wiki/Michael_A._Jackson",
        "color": 0xE74C3C
    },
    {
        "quote": "Good programmers know what to write. Great ones know what to rewrite (and reuse).",
        "author": "Eric S. Raymond",
        "bio": "Open source advocate, author of 'The Cathedral and the Bazaar'",
        "wiki": "https://en.wikipedia.org/wiki/Eric_S._Raymond",
        "color": 0xFCC624
    },
    {
        "quote": "Often, the hard part isn't solving problems, but deciding what problems to solve.",
        "author": "Anonymous",
        "bio": "Software wisdom",
        "wiki": None,
        "color": 0x3498DB
    },
    {
        "quote": "Good design adds value faster than it adds cost.",
        "author": "Thomas C. Gale",
        "bio": "Designer",
        "wiki": None,
        "color": 0x16A085
    },
    {
        "quote": "There's a big difference between making a simple product & making a product simple.",
        "author": "Des Traynor",
        "bio": "Co-founder of Intercom",
        "wiki": None,
        "color": 0x3498DB
    },
    {
        "quote": "If you're not prepared to be wrong, you'll never come up with anything original.",
        "author": "Ken Robinson",
        "bio": "Author and creativity expert",
        "wiki": "https://en.wikipedia.org/wiki/Ken_Robinson_(educationalist)",
        "color": 0x9B59B6
    },
    {
        "quote": "The best way to get a project done faster is to start sooner.",
        "author": "Jim Highsmith",
        "bio": "Software engineer and author",
        "wiki": None,
        "color": 0x27AE60
    },
    {
        "quote": "Quality is never an accident. It is always the result of intelligent effort.",
        "author": "John Ruskin",
        "bio": "Art critic (often applied to software)",
        "wiki": "https://en.wikipedia.org/wiki/John_Ruskin",
        "color": 0x2ECC71
    },
    {
        "quote": "There are two ways to write error-free programs; only the third works.",
        "author": "Alan J. Perlis",
        "bio": "First recipient of the Turing Award",
        "wiki": "https://en.wikipedia.org/wiki/Alan_Perlis",
        "color": 0x16A085
    },
    {
        "quote": "You can't have great software without a great team, and most software teams behave like dysfunctional families.",
        "author": "Jim McCarthy",
        "bio": "Software manager and author",
        "wiki": None,
        "color": 0xE67E22
    },
    {
        "quote": "Software testing is not an exercise; it's an investment in quality.",
        "author": "Anonymous",
        "bio": "Quality assurance wisdom",
        "wiki": None,
        "color": 0x2ECC71
    },
    {
        "quote": "Programming is like writing a book... except if you miss out a single comma on page 126 the whole thing makes no damn sense.",
        "author": "Anonymous",
        "bio": "Programming humor",
        "wiki": None,
        "color": 0xE67E22
    },
    {
        "quote": "The computer is incredibly fast, accurate and stupid. Man is unbelievably slow, inaccurate and brilliant. The marriage of the two is a force beyond calculation.",
        "author": "Leo Cherne",
        "bio": "Economist and public servant",
        "wiki": "https://en.wikipedia.org/wiki/Leo_Cherne",
        "color": 0x9B59B6
    },
    {
        "quote": "Privacy is not about having something to hide. Privacy is about having something to protect.",
        "author": "Elissa Shevinsky",
        "bio": "Privacy advocate, entrepreneur, and author of 'Lean Out'",
        "wiki": None,
        "color": 0x9B59B6
    },
    {
        "quote": "The best minds of my generation are thinking about how to make people click ads. That sucks.",
        "author": "Elissa Shevinsky",
        "bio": "Privacy advocate, entrepreneur, and author of 'Lean Out'",
        "wiki": None,
        "color": 0x9B59B6
    },
    {
        "quote": "We need to build technology that respects human dignity and autonomy.",
        "author": "Elissa Shevinsky",
        "bio": "Privacy advocate, entrepreneur, and author of 'Lean Out'",
        "wiki": None,
        "color": 0x9B59B6
    },
    {
        "quote": "Security is not a product, but a process. Privacy is not just a feature, it's a human right.",
        "author": "Elissa Shevinsky",
        "bio": "Privacy advocate, entrepreneur, and author of 'Lean Out'",
        "wiki": None,
        "color": 0x9B59B6
    },
    {
        "quote": "The only way to build ethical technology is to put ethics first, not as an afterthought.",
        "author": "Elissa Shevinsky",
        "bio": "Privacy advocate, entrepreneur, and author of 'Lean Out'",
        "wiki": None,
        "color": 0x9B59B6
    },
    {
        "quote": "Just as the printing press altered the power of medieval guilds and the social power structure, so too will cryptologic methods fundamentally alter the nature of corporations and of government interference in economic transactions.",
        "author": "Timothy C. May",
        "bio": "Cryptoanarchist, cypherpunk pioneer, author of 'The Crypto Anarchist Manifesto'",
        "wiki": "https://en.wikipedia.org/wiki/Timothy_C._May",
        "color": 0x2C3E50
    },
    {
        "quote": "The State will of course try to slow or halt the spread of this technology, citing national security concerns, use of the technology by drug dealers and tax evaders, and fears of societal disintegration.",
        "author": "Timothy C. May",
        "bio": "Cryptoanarchist, cypherpunk pioneer, author of 'The Crypto Anarchist Manifesto'",
        "wiki": "https://en.wikipedia.org/wiki/Timothy_C._May",
        "color": 0x2C3E50
    },
    {
        "quote": "Crypto anarchy is the cyberspatial realization of anarcho-capitalism, transcending national boundaries and freeing individuals to make the economic arrangements they wish.",
        "author": "Timothy C. May",
        "bio": "Cryptoanarchist, cypherpunk pioneer, author of 'The Crypto Anarchist Manifesto'",
        "wiki": "https://en.wikipedia.org/wiki/Timothy_C._May",
        "color": 0x2C3E50
    },
    {
        "quote": "A specter is haunting the modern world, the specter of crypto anarchy.",
        "author": "Timothy C. May",
        "bio": "Cryptoanarchist, cypherpunk pioneer, author of 'The Crypto Anarchist Manifesto'",
        "wiki": "https://en.wikipedia.org/wiki/Timothy_C._May",
        "color": 0x2C3E50
    },
    {
        "quote": "Cypherpunks write code.",
        "author": "Timothy C. May",
        "bio": "Cryptoanarchist, cypherpunk pioneer, author of 'The Crypto Anarchist Manifesto'",
        "wiki": "https://en.wikipedia.org/wiki/Timothy_C._May",
        "color": 0x2C3E50
    },
    {
        "quote": "Strong cryptography can resist an unlimited application of violence. No amount of coercive force will ever solve a math problem.",
        "author": "Timothy C. May",
        "bio": "Cryptoanarchist, cypherpunk pioneer, author of 'The Crypto Anarchist Manifesto'",
        "wiki": "https://en.wikipedia.org/wiki/Timothy_C._May",
        "color": 0x2C3E50
    },
    {
        "quote": "The technology for electronic privacy exists. But the political will to protect it is another matter.",
        "author": "Timothy C. May",
        "bio": "Cryptoanarchist, cypherpunk pioneer, author of 'The Crypto Anarchist Manifesto'",
        "wiki": "https://en.wikipedia.org/wiki/Timothy_C._May",
        "color": 0x2C3E50
    },
]


class PaginatorView(View):
    """View for paginated embeds with navigation buttons."""
    
    def __init__(self, pages: list[discord.Embed], timeout: int = 180):
        super().__init__(timeout=timeout)
        self.pages = pages
        self.current_page = 0
        self.message = None
        self._update_buttons()
    
    def _update_buttons(self):
        """Update button states based on current page."""
        self.first_page.disabled = self.current_page == 0
        self.prev_page.disabled = self.current_page == 0
        self.next_page.disabled = self.current_page == len(self.pages) - 1
        self.last_page.disabled = self.current_page == len(self.pages) - 1
    
    @discord.ui.button(label="⏮️", style=discord.ButtonStyle.gray)
    async def first_page(self, interaction: discord.Interaction, button: Button):
        """Go to first page."""
        self.current_page = 0
        self._update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)
    
    @discord.ui.button(label="◀️", style=discord.ButtonStyle.primary)
    async def prev_page(self, interaction: discord.Interaction, button: Button):
        """Go to previous page."""
        self.current_page -= 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)
    
    @discord.ui.button(label="▶️", style=discord.ButtonStyle.primary)
    async def next_page(self, interaction: discord.Interaction, button: Button):
        """Go to next page."""
        self.current_page += 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)
    
    @discord.ui.button(label="⏭️", style=discord.ButtonStyle.gray)
    async def last_page(self, interaction: discord.Interaction, button: Button):
        """Go to last page."""
        self.current_page = len(self.pages) - 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)
    
    @discord.ui.button(label="🗑️", style=discord.ButtonStyle.danger)
    async def delete(self, interaction: discord.Interaction, button: Button):
        """Delete the message."""
        await interaction.message.delete()
    
    async def on_timeout(self):
        """Disable all buttons when the view times out."""
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except:
                pass


class TechQuote(commands.Cog):
    """Tech Quote of the Day - Wisdom from tech legends."""
    
    def __init__(self, bot):
        self.bot = bot
    
    def _create_quote_embed(self, quote_data: dict) -> discord.Embed:
        """
        Create a Discord embed for a tech quote.
        
        Args:
            quote_data: Quote data dictionary
            
        Returns:
            Discord embed with quote and author info
        """
        embed = discord.Embed(
            title="💡 Tech Quote of the Day",
            description=f'"{quote_data["quote"]}"',
            color=quote_data.get("color", 0x5865F2)  # Discord blurple default
        )
        
        # Add author information
        author_text = f"— {quote_data['author']}"
        if quote_data.get('bio'):
            author_text += f"\n*{quote_data['bio']}*"
        
        embed.add_field(name="", value=author_text, inline=False)
        
        # Add Wikipedia link if available
        if quote_data.get('wiki'):
            embed.add_field(
                name="📖 Learn More",
                value=f"[Read about {quote_data['author']}]({quote_data['wiki']})",
                inline=False
            )
        
        embed.set_footer(text="🐧 Penguin Overlord | Tech Wisdom")
        
        return embed
    
    @commands.hybrid_command(name='techquote', description='Get a random tech quote')
    async def techquote(self, ctx: commands.Context):
        """
        Get a random quote from tech legends.
        
        Usage:
            !techquote
            /techquote
        """
        quote_data = random.choice(TECH_QUOTES)
        embed = self._create_quote_embed(quote_data)
        await ctx.send(embed=embed)
    
    @commands.hybrid_command(name='quote_linus', description='Get a quote from Linus Torvalds')
    async def quote_linus(self, ctx: commands.Context):
        """
        Get a quote from Linus Torvalds.
        
        Usage:
            !quote_linus
            /quote_linus
        """
        linus_quotes = [q for q in TECH_QUOTES if q['author'] == 'Linus Torvalds']
        if linus_quotes:
            quote_data = random.choice(linus_quotes)
            embed = self._create_quote_embed(quote_data)
            await ctx.send(embed=embed)
        else:
            await ctx.send("No quotes from Linus Torvalds found!")
    
    @commands.hybrid_command(name='quote_stallman', description='Get a quote from Richard Stallman')
    async def quote_stallman(self, ctx: commands.Context):
        """
        Get a quote from Richard Stallman.
        
        Usage:
            !quote_stallman
            /quote_stallman
        """
        stallman_quotes = [q for q in TECH_QUOTES if q['author'] == 'Richard Stallman']
        if stallman_quotes:
            quote_data = random.choice(stallman_quotes)
            embed = self._create_quote_embed(quote_data)
            await ctx.send(embed=embed)
        else:
            await ctx.send("No quotes from Richard Stallman found!")
    
    @commands.hybrid_command(name='quote_hopper', description='Get a quote from Grace Hopper')
    async def quote_hopper(self, ctx: commands.Context):
        """
        Get a quote from Grace Hopper.
        
        Usage:
            !quote_hopper
            /quote_hopper
        """
        hopper_quotes = [q for q in TECH_QUOTES if q['author'] == 'Grace Hopper']
        if hopper_quotes:
            quote_data = random.choice(hopper_quotes)
            embed = self._create_quote_embed(quote_data)
            await ctx.send(embed=embed)
        else:
            await ctx.send("No quotes from Grace Hopper found!")
    
    @commands.hybrid_command(name='quote_shevinsky', description='Get a quote from Elissa Shevinsky')
    async def quote_shevinsky(self, ctx: commands.Context):
        """
        Get a random quote from Elissa Shevinsky, privacy advocate and entrepreneur.
        
        Usage:
            !quote_shevinsky
            /quote_shevinsky
        """
        shevinsky_quotes = [q for q in TECH_QUOTES if q['author'] == 'Elissa Shevinsky']
        if shevinsky_quotes:
            quote_data = random.choice(shevinsky_quotes)
            embed = self._create_quote_embed(quote_data)
            await ctx.send(embed=embed)
        else:
            await ctx.send("No quotes from Elissa Shevinsky found!")
    
    @commands.hybrid_command(name='quote_may', description='Get a quote from Timothy C. May')
    async def quote_may(self, ctx: commands.Context):
        """
        Get a random quote from Timothy C. May, cryptoanarchist and cypherpunk pioneer.
        
        Usage:
            !quote_may
            /quote_may
        """
        may_quotes = [q for q in TECH_QUOTES if q['author'] == 'Timothy C. May']
        if may_quotes:
            quote_data = random.choice(may_quotes)
            embed = self._create_quote_embed(quote_data)
            await ctx.send(embed=embed)
        else:
            await ctx.send("No quotes from Timothy C. May found!")
    
    @commands.hybrid_command(name='quote_list', description='List all available tech quote authors')
    async def quote_list(self, ctx: commands.Context):
        """
        List all tech legends with quotes in the database.
        
        Usage:
            !quote_list
            /quote_list
        """
        # Get unique authors
        authors = {}
        for quote in TECH_QUOTES:
            author = quote['author']
            if author not in authors:
                authors[author] = {
                    'bio': quote.get('bio', 'Tech legend'),
                    'count': 0
                }
            authors[author]['count'] += 1
        
        # Sort by quote count
        sorted_authors = sorted(authors.items(), key=lambda x: x[1]['count'], reverse=True)
        
        # Build author list lines
        author_lines = []
        for author, data in sorted_authors:
            author_lines.append(f"**{author}** — {data['bio']} ({data['count']} quote{'s' if data['count'] > 1 else ''})")
        
        # Paginate to avoid Discord's embed field limit (1024 chars per field)
        # We'll split into chunks that fit within embed field limits
        max_chars = 900  # Safe limit for embed field (Discord limit is 1024)
        page_content = []
        current_page = []
        current_length = 0
        
        for line in author_lines:
            line_length = len(line) + 1  # +1 for newline
            if current_length + line_length > max_chars and current_page:
                page_content.append(current_page)
                current_page = []
                current_length = 0
            current_page.append(line)
            current_length += line_length
        
        if current_page:
            page_content.append(current_page)
        
        # Create embed pages
        embeds = []
        for i, page in enumerate(page_content, start=1):
            embed = discord.Embed(
                title="💡 Tech Quote Authors",
                description=f"We have quotes from {len(authors)} tech legends (Total: {len(TECH_QUOTES)} quotes)\nPage {i} of {len(page_content)}",
                color=0x5865F2
            )
            embed.add_field(name="", value="\n".join(page), inline=False)
            embed.set_footer(text="Use !techquote to get a random quote! • Use buttons to navigate")
            embeds.append(embed)
        
        # Send with paginator if multiple pages, otherwise just send the embed
        if len(embeds) > 1:
            view = PaginatorView(embeds)
            message = await ctx.send(embed=embeds[0], view=view)
            view.message = message
        else:
            await ctx.send(embed=embeds[0])


async def setup(bot):
    """Load the TechQuote cog."""
    await bot.add_cog(TechQuote(bot))
    logger.info("TechQuote cog loaded")
