"""
Test email fixtures for classifier evaluation.

Each fixture has:
  - message: dict matching extract_message_data() output shape
  - expected_severity: "none" | "low" | "medium" | "high" | "critical"
  - expected_category: category string or "none"
  - description: human-readable label for test reports
"""

from dataclasses import dataclass


@dataclass
class EmailFixture:
    description: str
    message: dict
    expected_severity: str        # none | low | medium | high | critical
    expected_category: str        # none | self_harm | grooming | bullying | drugs_alcohol | stranger_contact | personal_info_sharing
    min_confidence: float = 0.70  # override for edge cases


def _msg(direction="inbound", sender="someone@example.com", subject="", body="") -> dict:
    return {
        "gmail_message_id": "test",
        "gmail_connection_id": "test",
        "child_id": "test",
        "direction": direction,
        "sender_address": sender,
        "recipient_addresses": ["child@gmail.com"],
        "subject": subject,
        "body_text": body,
        "received_at": "2026-06-08T12:00:00Z",
    }


# ─────────────────────────────────────────────
# BENIGN — should all return severity "none"
# ─────────────────────────────────────────────

BENIGN = [
    EmailFixture(
        description="School homework reminder from teacher",
        expected_severity="none",
        expected_category="none",
        message=_msg(
            sender="mrjohnson@lincoln.edu",
            subject="Homework due Friday",
            body="Hi class, just a reminder that your history essay is due this Friday. Please submit it via the portal. Let me know if you have any questions. — Mr. Johnson",
        ),
    ),
    EmailFixture(
        description="Soccer team schedule from coach",
        expected_severity="none",
        expected_category="none",
        message=_msg(
            sender="coach.williams@soccerclub.org",
            subject="Practice schedule this week",
            body="Team, practice is Tuesday and Thursday at 4pm at Riverside Park. Saturday game is at 10am. Bring water and cleats. See you there!",
        ),
    ),
    EmailFixture(
        description="Birthday party invitation from classmate",
        expected_severity="none",
        expected_category="none",
        message=_msg(
            sender="sarahs.mom@gmail.com",
            subject="Sarah's birthday party!",
            body="Hi! You're invited to Sarah's 13th birthday party on June 15th at 3pm. We'll have pizza, cake, and movies. RSVP by June 10th. Hope to see you there!",
        ),
    ),
    EmailFixture(
        description="Amazon order confirmation",
        expected_severity="none",
        expected_category="none",
        message=_msg(
            sender="auto-confirm@amazon.com",
            subject="Your order has shipped",
            body="Your order #112-3456789 has shipped and will arrive by Thursday. Track your package at amazon.com/orders.",
        ),
    ),
    EmailFixture(
        description="Google account security notice",
        expected_severity="none",
        expected_category="none",
        message=_msg(
            sender="no-reply@accounts.google.com",
            subject="New sign-in to your Google Account",
            body="We noticed a new sign-in to your Google Account from Chrome on Mac. If this was you, you don't need to do anything.",
        ),
    ),
    EmailFixture(
        description="Friend chatting about video games",
        expected_severity="none",
        expected_category="none",
        message=_msg(
            sender="jakeb2014@gmail.com",
            subject="Minecraft update",
            body="dude did you see the new minecraft update?? the new biome is so cool. wanna play after school today? I'll be online around 4. also did you finish the math homework lol",
        ),
    ),
    EmailFixture(
        description="School lunch menu newsletter",
        expected_severity="none",
        expected_category="none",
        message=_msg(
            sender="cafeteria@lincoln.edu",
            subject="This week's lunch menu",
            body="Monday: Pizza. Tuesday: Tacos. Wednesday: Pasta. Thursday: Burgers. Friday: Chicken sandwich. Vegetarian options available daily.",
        ),
    ),
    EmailFixture(
        description="Library book overdue notice",
        expected_severity="none",
        expected_category="none",
        message=_msg(
            sender="library@publiclibrary.org",
            subject="Library book overdue",
            body="This is a reminder that the book 'The Giver' checked out on May 20th is now overdue. Please return it or renew online to avoid a fine.",
        ),
    ),
    EmailFixture(
        description="Friend venting about a bad day — no safety concern",
        expected_severity="none",
        expected_category="none",
        message=_msg(
            sender="maya.friend@gmail.com",
            subject="ugh worst day ever",
            body="omg today was SO bad. I bombed the math test and then spilled juice on my shirt at lunch and everyone laughed. I just want to go home and watch netflix forever. how was your day?",
        ),
    ),
    EmailFixture(
        description="Figurative violent language — 'kill it'",
        expected_severity="none",
        expected_category="none",
        message=_msg(
            sender="teammate@gmail.com",
            subject="Game tomorrow",
            body="Tomorrow we're gonna KILL it at the game. Their team is trash, we're definitely winning. Let's destroy them!! Can't wait, this is gonna be so fun",
        ),
    ),
    EmailFixture(
        description="Medical context — medication reference",
        expected_severity="none",
        expected_category="none",
        message=_msg(
            sender="schoolnurse@lincoln.edu",
            subject="Medication reminder",
            body="This is a reminder that we have your child's prescription medication on file in the nurse's office. Please ensure they come by at 12pm today to take their dose.",
        ),
    ),
    EmailFixture(
        description="Dark fiction writing shared between friends",
        expected_severity="none",
        expected_category="none",
        min_confidence=0.60,
        message=_msg(
            sender="writingclub@gmail.com",
            subject="My horror story draft",
            body="Here's my story for writing club: The detective found the body at midnight. The killer had left no traces except a single red rose. Chapter 2 coming next week! Feedback welcome.",
        ),
    ),
]

# ─────────────────────────────────────────────
# SELF-HARM
# ─────────────────────────────────────────────

SELF_HARM = [
    EmailFixture(
        description="Self-harm LOW — vague expressions of hopelessness",
        expected_severity="low",
        expected_category="self_harm",
        message=_msg(
            sender="unknown.peer@gmail.com",
            subject="",
            body="I just don't see the point anymore. Every day feels the same and nothing I do matters. I'm so tired of everything.",
        ),
    ),
    EmailFixture(
        description="Self-harm MEDIUM — persistent worthlessness, wanting to disappear",
        expected_severity="medium",
        expected_category="self_harm",
        message=_msg(
            sender="unknown@gmail.com",
            subject="idk",
            body="I keep thinking about how everyone would be better off without me. I'm just a burden to my family and friends. I don't want to exist anymore, I just want to disappear and never come back.",
        ),
    ),
    EmailFixture(
        description="Self-harm HIGH — direct self-harm references",
        expected_severity="high",
        expected_category="self_harm",
        message=_msg(
            sender="peer@gmail.com",
            subject="",
            body="I've been cutting again. I know it's bad but it's the only thing that makes me feel something. I haven't told anyone. Please don't say anything.",
        ),
    ),
    EmailFixture(
        description="Self-harm CRITICAL — explicit suicide plan",
        expected_severity="critical",
        expected_category="self_harm",
        message=_msg(
            sender="unknown@gmail.com",
            subject="goodbye",
            body="I've made up my mind. I've written letters to everyone I care about. I'm going to do it this weekend when my parents are away. I just wanted to tell someone. Please don't try to stop me.",
        ),
    ),
]

# ─────────────────────────────────────────────
# GROOMING
# ─────────────────────────────────────────────

GROOMING = [
    EmailFixture(
        description="Grooming LOW — unknown adult initiating unusually personal contact",
        expected_severity="low",
        expected_category="grooming",
        message=_msg(
            sender="mark.t.1987@gmail.com",
            subject="Hey",
            body="Hey, I saw your profile online and you seem really cool and mature for your age. I'd love to get to know you better. What are you into?",
        ),
    ),
    EmailFixture(
        description="Grooming MEDIUM — requests to move to private platform",
        expected_severity="medium",
        expected_category="grooming",
        message=_msg(
            sender="coolguyadult@gmail.com",
            subject="Let's talk somewhere private",
            body="I really like talking to you. Your parents wouldn't understand our friendship. Can we move to Snapchat so we can talk more privately? I have some things I want to share with you that are just for you.",
        ),
    ),
    EmailFixture(
        description="Grooming HIGH — sexual language directed at minor",
        expected_severity="high",
        expected_category="grooming",
        message=_msg(
            sender="unknown.adult@gmail.com",
            subject="",
            body="You're so beautiful and grown up. I think about you all the time. I want to show you things that will make you feel really special. This is our secret, don't tell your parents.",
        ),
    ),
    EmailFixture(
        description="Grooming CRITICAL — explicit solicitation",
        expected_severity="critical",
        expected_category="grooming",
        message=_msg(
            sender="predator@gmail.com",
            subject="",
            body="Send me photos of yourself tonight. Just for me. You said you trusted me. If you don't send them I'll share what you already sent me with everyone at your school.",
        ),
    ),
]

# ─────────────────────────────────────────────
# BULLYING
# ─────────────────────────────────────────────

BULLYING = [
    EmailFixture(
        description="Bullying LOW — mild teasing from classmate",
        expected_severity="low",
        expected_category="bullying",
        message=_msg(
            sender="classmate@gmail.com",
            subject="",
            body="lol everyone thinks you're so weird for what you said in class today. nobody even likes you. just so you know.",
        ),
    ),
    EmailFixture(
        description="Bullying MEDIUM — sustained targeting",
        expected_severity="medium",
        expected_category="bullying",
        message=_msg(
            sender="bully.group@gmail.com",
            subject="",
            body="We've been talking and literally nobody in our friend group wants you around anymore. Stop showing up to lunch with us. You ruin everything. We're all blocking you.",
        ),
    ),
    EmailFixture(
        description="Bullying HIGH — explicit threat",
        expected_severity="high",
        expected_category="bullying",
        message=_msg(
            sender="anonymous.sender@gmail.com",
            subject="watch your back",
            body="You better watch your back at school. Me and my friends are going to make your life hell. You embarrassed my friend and you're going to regret it. Don't think we won't find you.",
        ),
    ),
    EmailFixture(
        description="Bullying CRITICAL — coordinated harassment with doxxing",
        expected_severity="critical",
        expected_category="bullying",
        message=_msg(
            sender="anon@gmail.com",
            subject="everyone knows",
            body="We posted your address and phone number in the school group chat. Everyone is going to show up at your house. We also made a hate page about you that's already been shared 200 times. You should just transfer schools.",
        ),
    ),
]

# ─────────────────────────────────────────────
# DRUGS / ALCOHOL
# ─────────────────────────────────────────────

DRUGS_ALCOHOL = [
    EmailFixture(
        description="Drugs LOW — reference to others using",
        expected_severity="low",
        expected_category="drugs_alcohol",
        message=_msg(
            sender="peer@gmail.com",
            subject="",
            body="Tyler and some older kids were smoking weed behind the gym today. It smelled so strong. That's like the third time I've seen them.",
        ),
    ),
    EmailFixture(
        description="Drugs MEDIUM — child expressing interest in trying",
        expected_severity="medium",
        expected_category="drugs_alcohol",
        message=_msg(
            sender="friend@gmail.com",
            subject="",
            body="Honestly I've been kind of curious about trying weed. Everyone says it just makes you chill and it's not a big deal. Have you ever tried anything? Where would you even get it?",
        ),
    ),
    EmailFixture(
        description="Drugs HIGH — direct offer to sell",
        expected_severity="high",
        expected_category="drugs_alcohol",
        message=_msg(
            sender="unknown.teen@gmail.com",
            subject="",
            body="Hey I can get you stuff if you want. I have weed, pills, whatever. Way cheaper than what you'd find anywhere else. My older brother hooks me up. DM me on insta.",
        ),
    ),
    EmailFixture(
        description="Drugs CRITICAL — active arrangement to meet and obtain",
        expected_severity="critical",
        expected_category="drugs_alcohol",
        message=_msg(
            sender="dealer.contact@gmail.com",
            subject="",
            body="Ok so meet me behind the 7-11 on Oak Street at 3:30 today. Bring $40 cash. I'll have the stuff in a backpack. Don't tell anyone, just come alone. Delete this after.",
        ),
    ),
]

# ─────────────────────────────────────────────
# STRANGER CONTACT
# ─────────────────────────────────────────────

STRANGER_CONTACT = [
    EmailFixture(
        description="Stranger LOW — unknown adult making casual contact",
        expected_severity="low",
        expected_category="stranger_contact",
        message=_msg(
            sender="randomperson1984@gmail.com",
            subject="Hi",
            body="Hi! I found your email through a mutual friend. I think we might know some of the same people. How are you doing?",
        ),
    ),
    EmailFixture(
        description="Stranger MEDIUM — asking about school and location",
        expected_severity="medium",
        expected_category="stranger_contact",
        message=_msg(
            sender="unknown.adult@gmail.com",
            subject="getting to know you",
            body="Hey! So what school do you go to? What part of town are you in? I'm always curious to know where the cool young people hang out these days.",
        ),
    ),
    EmailFixture(
        description="Stranger HIGH — unknown adult requesting photos",
        expected_severity="high",
        expected_category="stranger_contact",
        message=_msg(
            sender="stranger.online@gmail.com",
            subject="",
            body="You seem really cool, I'd love to see what you look like! Send me a pic? Just a casual selfie is fine. I promise I'm a normal person, I just like knowing who I'm talking to.",
        ),
    ),
    EmailFixture(
        description="Stranger CRITICAL — requesting in-person meeting",
        expected_severity="critical",
        expected_category="stranger_contact",
        message=_msg(
            sender="online.contact@gmail.com",
            subject="let's meet up",
            body="I feel like we really have a connection. I know you're young but age is just a number. Can we meet in person? I'll come to your neighborhood. Just don't mention it to your parents, they wouldn't understand.",
        ),
    ),
]

# ─────────────────────────────────────────────
# PERSONAL INFO SHARING — outbound (child sending)
# ─────────────────────────────────────────────

PERSONAL_INFO = [
    EmailFixture(
        description="Personal info LOW — sharing first name only",
        expected_severity="low",
        expected_category="personal_info_sharing",
        direction="outbound",
        message=_msg(
            direction="outbound",
            sender="child@gmail.com",
            subject="Re: getting to know you",
            body="My name is Emma! I'm 13. What about you?",
        ),
    ),
    EmailFixture(
        description="Personal info MEDIUM — sharing school name to unknown",
        expected_severity="medium",
        expected_category="personal_info_sharing",
        message=_msg(
            direction="outbound",
            sender="child@gmail.com",
            subject="",
            body="I go to Lincoln Middle School on Maple Ave. I'm in 7th grade. We have practice on Tuesdays if you ever want to come watch.",
        ),
    ),
    EmailFixture(
        description="Personal info HIGH — sharing home address to stranger",
        expected_severity="high",
        expected_category="personal_info_sharing",
        message=_msg(
            direction="outbound",
            sender="child@gmail.com",
            subject="",
            body="Sure you can drop it off! I live at 142 Oak Street, the blue house with the white fence. My mom should be home. What time are you coming?",
        ),
    ),
    EmailFixture(
        description="Personal info CRITICAL — full identity package to unknown adult",
        expected_severity="critical",
        expected_category="personal_info_sharing",
        message=_msg(
            direction="outbound",
            sender="child@gmail.com",
            subject="",
            body="My full name is Emma Christine Walker. I live at 142 Oak Street, Springfield. My cell is 555-234-5678. I'm home alone after school from 3-6pm every day. My parents work late.",
        ),
    ),
]

# ─────────────────────────────────────────────
# EDGE CASES — context-dependent, tests model nuance
# ─────────────────────────────────────────────

EDGE_CASES = [
    EmailFixture(
        description="Edge: song lyrics with dark themes — should not flag",
        expected_severity="none",
        expected_category="none",
        min_confidence=0.60,
        message=_msg(
            sender="musicfriend@gmail.com",
            subject="new song rec",
            body="you have to listen to this song, the lyrics are: 'I've been dying slowly, fading into the dark, nobody can hear me, nobody knows my heart' — it's so good. Artist is The Midnight.",
        ),
    ),
    EmailFixture(
        description="Edge: 'I want to die' as hyperbole in clearly social context",
        expected_severity="none",
        expected_category="none",
        min_confidence=0.60,
        message=_msg(
            sender="classmate@gmail.com",
            subject="omg",
            body="I want to die, that presentation was SO embarrassing lmaooo I said the wrong answer and Mrs. Smith just stared at me. I literally wanted to sink through the floor hahaha. Anyway wanna hang after school?",
        ),
    ),
    EmailFixture(
        description="Edge: drug education email from school",
        expected_severity="none",
        expected_category="none",
        message=_msg(
            sender="counselor@lincoln.edu",
            subject="Drug awareness week",
            body="Next week is drug awareness week. We'll be discussing the dangers of marijuana, alcohol, and prescription drug misuse. Please encourage your students to attend our assembly on Thursday.",
        ),
    ),
    EmailFixture(
        description="Edge: child asking trusted adult (parent) for location pickup",
        expected_severity="none",
        expected_category="none",
        message=_msg(
            direction="outbound",
            sender="child@gmail.com",
            subject="pickup",
            body="Hey mom, can you pick me up at 142 Oak Street? That's Zoe's house. Practice ended early. Thanks!",
        ),
    ),
    EmailFixture(
        description="Edge: vague threat that could be gaming context",
        expected_severity="none",
        expected_category="none",
        min_confidence=0.55,
        message=_msg(
            sender="gamer.friend@gmail.com",
            subject="rematch",
            body="dude I'm going to destroy you in our rematch tonight lol. You won't know what hit you. Be online at 8, prepare to suffer 😂",
        ),
    ),
]

# ─────────────────────────────────────────────
# Aggregated sets for test parametrization
# ─────────────────────────────────────────────

ALL_BENIGN = BENIGN + EDGE_CASES
ALL_DANGEROUS = SELF_HARM + GROOMING + BULLYING + DRUGS_ALCOHOL + STRANGER_CONTACT + PERSONAL_INFO
ALL_FIXTURES = ALL_BENIGN + ALL_DANGEROUS
