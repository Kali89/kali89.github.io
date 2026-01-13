---
layout: post
title: "People as Harmonic Oscillators"
date: 2026-01-13
tags: [data, psychology]
---

I'm going to share a graph with you that I've been hawking around, in the vain
(but thus far ultimately fruitless) attempt to get *somebody* to care. I'd like
to start off with my former life (that of a guitar teacher, and of a physicist)
and remind you of the harmonic series that you get when you pluck a guitar
string:

Neat, right? You get a peak at halfway, and then a peak halfway between that,
and then a peak halfway between that...

On a guitar, these are (imaginatvely) called "harmonics" and sound clear and
pure and a little like a bell.

## Mobile Phone Data

A large part of my DPhil is based around a dataset of the app open and close
data of approximately 1.4 million Americans. **Of course** there are a million
interesting things we can do with that data but I'd like to focus in on
behaviour with one very specific app: the alarm clock app.

When we look at the distribution of usage of that app by minute of day
(ensuring we're using a person's local time), we see
a really cool picture:

![The alarm app opening behaviour of 1.4 million Americans over 2
years](/assets/images/long_range_alarm.png)

If we zoom in a little further, we can start to see a huge spike of activity in
the alarm app at 6am. I hope it's not too much of stretch to say that I think
we're glimpsing when people's alarms are set for in the morning. If we track
individual people, we can see snooze patterns. 

![A zoomed in view of the alarm app opening behaviour of 1.4 million Americans over 2
years](/assets/images/zoomed_alarm.png)

However, if you're like me then you probably noticed the lovely little sawtooth
pattern. It looks like people *really* like setting their alarm clock for
o'clock, and really don't like setting their alarm clock for one minute past
the hour.

If we expand on that a little bit, let's group **all** activity across the
entire time period by the minute of the hour. 


![The minute-of-hour of alarm opening behaviour of 1.4 million Americans over 2
years](/assets/images/grouped_alarm.png)

Cool, right? It looks suspisciously like the harmonic graph from up above. It
turns out, not only does nature like the nice even spacing that comes from
repetitive halving...people do too.

## (Data) Science for Fun

I don't know what to do with this *result*. The reason I did it was because I
noticed something funny, investigated further, and found something interesting
(to me, at least). But where does that live in the modern scientific world?

There are journals, but are journals interested in a snippet of a result like
this without a broad thesis and interpretation on what it means about *"the
human conditition"*? Conferences? I kind of feel that's the same - unless I'm
(claiming to, at least) giving a major new result, I don't feel like they'd be
interested.

I think the problem I'm butting up against here is ultimately the
professionalisation of science. I don't want to denigrate the science industry
(and by that, I mean universities, journals, funding bodies, conferences - the
mechanics that surround academica), but increased specialisation has meant
have-a-go hobbyists like me don't have a neat place to go.

I did a bit of work on scaling laws of pubs in rural England a few years ago
and found the same - it was hard to work out exactly where I should share the
work, because ultimately I wasn't vying for anything. I didn't *need* a
publication to add to my CV. I didn't *need* funding. I wasn't building off of
a body of work because (as far as I could tell) there wasn't a long academic
background I was building off of.

This is why I love being a data scientist. With the same set of skills, you can do human geography
one day (which pubs per parish in rural England apparently is), psychology the
next (which I guess 'people as harmonics' is? Honestly, no idea). What I lack
(and maybe what all of us lack) is the theoretical grounding in each of these
disciplines: I don't know about the long and winding history of urban scaling
laws (or I didn't, before I tried to legitimise my rural work), or the
pscyhology of choice (again, having to learn that now) in order to 'ground' my
work in earlier theory.

But in all honesty, that's exhausting and takes a lot of time. Does the
machinery around legitimising data science work by grounding it in the academic
discipline add enough value to make it worthwhile?

## Conclusion

Look, I've done a little pontification and naval gazing about the fact that I
need to do a bunch of work to justify sharing my cool graphs. Work that I'd
rather not do. So instead, let's just bask in the glorious knowledge that
6:01am is a perfectly legitimate time to wake up, and a more rational species
would have a more 'normal' distribution of alarm times. But we aren't rational
and, amongst many other signals, I have the charts to proove it.
