---
layout: post
title: "Dashboards are bad (and you should feel bad)"
date: 2026-01-06
tags: [data science, dashboards]
---

For years and years I've been referencing a particularly excellent blog post -
[The laws of shitty
dashboards](https://www.bears-repeating.com/the-laws-of-shitty-dashboards) -
and I've finally decided to write something myself about why dashboards are
bad, and why you should feel bad about either asking for them, or, God forbid,
actually making them.<!--more-->

## The Purpose of a Dashboard

Firstly, let's consider *why* we might be building a dashboard. Typically I see
a dashboard come about through one of a few ways:

### My People aren't Data Driven enough

An executive (or at least somebody who has *'people'*) doesn't like what
they're seeing in their organisation, or at least needs to be seen to be making
changes. Data is cool, right? But their people aren't using data enough. Why
not? 

Well, it's probably because they can't even see the data. They need a
dashboard! I'll request one and then...

And then what? 

You see, let's imagine that we were building a product for some
users, and we were being all Y Combinator/Lean Startup about it. Did the
executive speak to their users (the people who the dashboard is nominally for?) and understand what their pain points are? Did they meticulously understand **why** their people aren't being 'data-driven'<sup>TM</sup>? Or did they in fact immediately assume they knew the answer to a poorly-defined problem, leap straight to a solution, and then say 'ship it' with conviction?

And so then you, dear data scientist, end up building a dashboard for somebody.
But it's not entirely clear who you're building it for. Is it for the
executive? They don't need it, of course. They're already data-driven. So it
must be for that executives 'people'. Except. Well, except they didn't ask for
it and probably don't really want it. Are you building it for you? You
certainly don't want it - surely anything would be preferable to building
something nobody has any intention of looking at?

But alas, senior executive has said they want a dashboard and so senior
executive is going to get a dashboard and in six months time when nobody has
looked at it, at best it'll get consigned to the annals of bad decisions and
quietly forgotten about. At worst, the lack of usage will be blamed on either
lack of visual polish or lack of 'options' and you'll have to spend a whole
bunch of time working on the dashboard nobody ever looks at.

### I want to save time myself

People keep asking me questions and I can't possibly answer all of them.
Therefore, I'll save myself a bunch of time and effort if I build a dashboard.

NO. No you won't. 

Sure I will, I hear you say. I get 10 questions a day that are a simple SQL
query, and if I just create a dashboard then people can use that and not ask me
and I'll have empowered stakeholders to self-serve (sounds pretty
promotion-coded, amirite?). 

This isn't solving anybody's problem but your own. **You** have a problem that
people are asking you questions and you have to run a SQL snippet every time
they do. Somehow, you think you can build a tool and then
this becomes somebody else's problem? How many of your stakeholders get
up in the morning and think "*Gee, I really wish I could lighten the load on
$DATA_PERSON$*"? 

You're asking stakeholders to change their behaviour in order to inconvenience
you less. And all you're offering them is...what? Reduced latency? The ability
to self-serve? The ability to apply filters? Colour me sceptical.

Now, lest it be said that I'm a monster, I think that this is a perfectly fine
reason to build a dashboard under one very specific set of circumstances. Those
circumstances require the dashboard to be **the very best** way of saving you
this time. Other options you should consider first include:
1. Just running the query and giving them a number. Re-running queries is
   trivial and it's rare that somebody has the endurance to care about a number
   every day/week for a long period of time.
2. Sharing the SQL snippet and getting them set up with access. Teach a man to
   fish and all that. Maybe they're too senior for this (though you'd be
   surprised - an exec who can SQL is pretty cool), or maybe your
   infrastructure is too locked down or whatever...but if you can, then you
   probably should.
3. A report that outputs only to you. To clarify, I mean that you set up a
   report but that report spits out the number to you and you copy/paste that
   number to your stakeholder. Why not go straight to the stakeholder? Because
   then you've built infrastructure that you need to maintain.
 4. A report that outputs to whoever. Reports seem to be out of fashion (why
    build a report when you could build a dashboard?) but I don't know why. I
    can speculate (dopamine rush, pretty pictures, real-time) but ultimately,
    if what you want to do is repeatedly deliver a number at a set
    cadence...well you're describing a report.

As you can see given our smorgasbord of options above...the situations in which
a dashboard is **the best** tool to answer a questions is...well I think it's
pretty rare.

### I want an overview/diagnostic

Everybody wants a command centre - an overview of the health of their little
(or big) ecosystem. I need metrics and I need trend lines so I can see things
go up and go down and then say "power failing in quadrant C, what are we doing
about this?" and sound like a starship commander.

Value++.

OK - slightly less cynically, of course you want an overview of the health of
your business, and it's nice to have graphical representations of that. What I
really want to push you on is this: 

**When was the last time you made a good decision as a result of looking at a
dashboard?**

Maybe you've got some answers. Good for you. Now for the trickier part.

**Could you have arrived at that decision without the dashboard?**

There are a plethora of **bad** decisions taken after looking at dashboards -
any time you see the slightest variation and panic and set off a chain of
work/changes based on random fluctuations and pat yourself on the back at being
so quick to respond...well, those are your bad decisions.

There are some **good** decisions that are taken after looking at dashboards -
any time you see a gradually unfolding trend and run an initiative/roll out a
fix that ultimately arrests that trend (or enhances it or whatever). However,
could you have done those things without a dashboard? I think yes.

To me, a dashboard shows a lack of precise thinking. *What* do we care about?
*How* do we expect it to move? And then is it moving in that way? These are
surgical questions that have specific answers. Maybe your command-centre
dashboard is exactly that - a well curated list of specific questions that are
well answered. More likely though, it's an over-large collection of
potentially relevant metrics that let you use your story-telling powers to come
up with '*causal*' explanations.

Not to delve too deep psychologically, but Daniel Kahneman's work positions
people as the ultimate story-tellers - give us a collection of facts and we'll
come up with a story to explain why that happened. Give us the opposite set of
facts and we'll come up with an equally plausible story. Then we latch onto the
story and forget the facts that we used to construct it. How is that relevant
here?

By giving people a command centre, you're giving them almost unlimited license
to come up with stories. Whether those stories are harmful or just neutral
largely depends on the company you work for.

Now again, I'm not a zealot (much). You should have one of these overview
dashboards. Somebody needs to know if you've lost 60% of your revenue in LATAM.
But I'm arguing two things:

1. You don't need **another** of those dashboards. If you already have the
   information somewhere, why do you need it again?
2. Somebody needs to notice whether or not you've lost 60% of your revenue in
   LATAM over the last few weeks...but should it really be the CEO browsing the
   command-centre overview? If you're a small start-up (cool), sure. If you're
   not...surely there's somebody else at the company who should be noticing
   these things?

How do they notice it, if not with a dashboard? If you're a senior leader, I
beg of you, please let that be their problem. Maybe they need a dashboard or
maybe they don't. Your job is to tell them that they should notice. Their job
is to work out how they want to do that.

I also want to briefly touch upon dashboard design in this: we data people have
to design those dashboards in a very specific way and it's nothing to do with
good data presentation. We need the lines to move a bit, but not too much. If
the lines don't move at all (we use yearly numbers or pick stable quantities)
then you don't like the dashboards because they don't give you that sweet sweet
dopamine. If they move too much then you can't tell *what's happening* (though
of course, that is exactly what's happening) - you can't build a coherent story
about the data. So muggins over here (me) says "Let's use weekly/monthly"...not
because that's necessarily the right granularity over which to evaluate the
data...but because that's what'll keep you coming back.

### I need to know if something broke

Probably an engineer or a marketer - somebody who has something that is always
on and is expected to keep running and not see any anomalous behaviour. They
need to know how many requests their service is getting, or what the latency is
of a certain process, or what they're spending on TikTok in Namibia. They point
to an outage or an overspend and say "we need a dashboard to track this".

Sorry, I like you and these are my least intolerable dashboards, but you probably don't. What you want is anomaly detection.

You have a fixed set of metrics and you need to know exactly when one of them
crosses a threshold that says "you've got a problem here". That problem is
clearly anomaly detection, and you are too valuable to spend your life looking
at graphs and trying to visually detect anomalies. You're better than that.
Believe in yourself.

I posit that a lot of the reason why engineers/marketers use dashboards for
this rather than anomaly detection is because they don't trust anomaly
detection, and I don't necessarily think that they're wrong. Anomaly detection
systems are hard to build and balancing false positives and false negatives is
more an art than a science.

My advice to data scientists - sit with the stakeholder and the graph and ask
them "which of these are anomalies that you'd like to have picked up and which
were just normal expected behaviour?" If they're good engineers/marketers who
know their systems, I'd hope they'd be able to tell you. I also hope they'd be
able to tell you what they did about the anomalies. That's especially important
because if they don't know, then what use is it you telling them that there's
an anomaly?

The reason I have sympathy with this is that plotting the graphs is probably
stage 1 of this process. Anomaly detection is probably stage 3. But in order to
build an anomaly detection system, I'd have to be convinced that people know
what to do when an anomaly detection system fires and that's hard to test
unless you build a dashboard. So *maybe* this is OK, as long as you ultimately
end up migrating away from the dashboard when appropriate.


## What can I do?

You're convinced (you're probably not, but :shrug:) and don't want to build/ask
for any more dashboards. What can you do to stop building them?

For everybody, start by asking better questions. When somebody asks for a dashboard, ask them
what they want to know. Then tell them that you'll email them the answer every
day for the next 100 days if they'd like, but only if they email back and tell
you what they did with the number.

If you're a PM/leader whose people need to be more data-driven, ask them why
they're not using data in order to make their decisions. Work with them to
understand what data they're missing and whether that data is easily
accessible. If it is, they might say that they're missing data but that isn't
the real reason.

For data folks, ask what problem this dashboard is designed to solve, then try to solve the
problem without the dashboard. You want to know if a value goes above a
threshold? Great, I'll ping you when that happens. You want to know how one
business line is doing against another over time? Great, here's a graph. You
want to know tomorrow too? Well it's not likely to have changed that much. You
want to know next week? Great, here's another graph.

Doesn't sound scalable? Do things that don't scale isn't just advice for trendy start-ups - it's advice
for building any kind of product. Make yourself integral to the processes that
*might* require a dashboard and I think you'll be surprised at how rarely a
dashboard is the answer.

### Isn't that pretty obstructionist?

I prefer the term 'customer-focussed'. A dashboard is a product and rule number
one of building products is "speak to the customer - understand what their
problem is, and solve it."

Building the first thing the customer asks for isn't building good products. If
the first thing the customer asks for is a dashboard, your job is to find out
what their problem is and to solve it in the most efficient way you possibly
can.

I generally view data people as decision support - our job is to help the
company make the best decisions possible. It's not obstructionist to realise
when people are asking for tools that will make their decisions worse. It's not
obstructionist to protect your own time, not working on a product that has no
chance of helping the company. At certain levels, it's your job to help steer
the bad ~~dashboard~~ product into a slightly better one. At certain levels, it's your job
not to build the bad ~~dashboard~~ product in the first place.

Don't be part of the problem - be part of the solution. Say no to dashboards
today.
