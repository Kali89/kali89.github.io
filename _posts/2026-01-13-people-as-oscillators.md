---
layout: post
title: "People as Harmonic Oscillators"
date: 2026-01-13
tags: [data, psychology]
---

I'm going to share a graph with you that I've been hawking around, in the vain
(but thus far ultimately fruitless) attempt to get *somebody* to care. I've got
a cool data set and have found what can only really be described as a
*neat* little result. <!--more-->

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
we're glimpsing when people's alarms are set for in the morning. This is when
Americans apparently wake up. That spike at 6am is a little earlier than I'd personally like to get up, but I can countenance the spike at 7am so I suppose we can let the industriousness of Americans slide for now. If you're especially interested in when people are waking up then we can zoom in a little and you'll see what I'm talking about:

![A zoomed in view of the alarm app opening behaviour of 1.4 million Americans over 2
years](/assets/images/zoomed_alarm.png)

However, if you're like me then you probably noticed the lovely little sawtooth
pattern. If this were a maths class you'd say that you'd expect to see an
approximately normal distribution around a point (say, 7am). Maybe
an alien species founded on rationality have their alarm clocks set like that.
I imagine hunter-gatherers had a normalish distribution of wake times
surrounding the sunrise. 

But that's not what we see here, is it? It looks like people *really* like setting their alarm clock for
o'clock, and really don't like setting their alarm clock for one minute past
the hour.

If we expand on that a little bit, let's group **all** activity across the
entire time period by the minute of the hour. 


![The minute-of-hour of alarm opening behaviour of 1.4 million Americans over 2
years](/assets/images/grouped_alarm.png)

Cool, right? 

Now before you get all hissy, this is **only** people who are using alarm
clocks to wake up. I'm not including those people that rise to Grieg's Morning
Mood while the sun bathes them majestically, or with a sharp dig of a small
child's foot accompanied by the joyful cry of "morning time!" (this is me)

I'm also not technically saying that this is when they get up - maybe they
snooze (I can see that in the data), or maybe they're just idly browsing the
clock app at 6am every day (don't we all?). But realistically, some (probably
large) proportion of Americans use their phone alarm to wake them, and this is
their story.

## Harmonics

Why do I say people are oscillators, then? Well I'm harking back to my old life
as a guitar teacher and physicist. When you subdivide a guitar string in two
(hover over fret 12) and pluck the string, you get a beautiful bell-like sound that we call a
"natural harmonic" (you can get artificial harmonics by 'pinching' the string
to artificially shorten it - best heard at about 3:08 in Hotel California).
This is because you form a standing wave on the string. However, if you
subdivide the string into 3 (fret 7) you also create a standing wave - it's
less loud and a different note, but it's the same idea. Similarly, any integer
division of the string leads to standing waves of varying frequencies (and thus
note) and magnitude (and thus volume). If you're after a song that uses these
heavily, I'd recommend Flying in a Blue Dream by Joe Satriani.

If you look at these graphically (which you can
[here](https://phys.libretexts.org/Bookshelves/Waves_and_Acoustics/Sound_-_An_Interactive_eBook_\(Forinash_and_Christian\)/10%3A_Strings/10.01%3A_Driven_String_and_Resonance/10.1.01%3A_String_Resonance) you'll find that the graph looks weirdly similar to the graph above, of when people set their alarm for. Just like strings, people seem drawn to clean fractions of the hour (half past, quarter past, 10 past etc.)

## Conclusion

That's the finding, then. It's not a thesis, and I've no idea what to do with
this academically but that wasn't really the point. The point was, it's
interesting and cool and I want to share it.

Let us bask in the glorious knowledge that 6:01am is a perfectly legitimate time to wake up, and a more rational species
might have a more 'normal' distribution of alarm times. But thankfully we aren't always perfectly rational and I'm glad that I've now got the graphs to prove it.
