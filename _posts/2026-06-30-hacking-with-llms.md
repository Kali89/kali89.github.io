---
layout: post
title: "Hacking with LLMs"
date: 2026-06-30
tags: [programming, data]
---

Over the last few months I've been spending a fair amount of time programming
and doing so with LLMs is _different_.<!--more--> Probably _better_. At least...for some kind of definition of better. It allows me to
achieve much more in a much less time which sounds like it'd be net positive. Simple idle questions can easily be
solved without much investment.

So, why don't I just outright say that it's better? Because I feel like you lose
something through LLM-based programming. I've produced something, but do I
really understand it? Often not. Let me give you an example of a project I
recently worked on...

## Morrisons More

My wife and I tend to shop at the Morrisons in Boroughbridge and they have a
loyalty card program (who doesn't)? When poking through that online account I
found that they have digital receipts, showing everything that I've bought at
Morrisons over the last year.

It's all rendered through a painful Javascript system so no raw HTML and each
Javascript call is protected with multiple authentication tokens and...well,
it'd be a pain. In the past, my options would either be to spend a long time
building something bespoke, manually copying and pasting all of the receipts
into a text file and then parsing, or giving up and accepting I'll never do
analytics on my purchases (or maybe make a GDPR request?)

Now, I fire up Claude Code and explain what I want and hey presto - 30 minutes
later and a few authentication tokens copied and I've got my entire shopping
history.

30 minutes later and I know how much milk I've bought over time and how that
changed with the addition of a new child. And what proportion of my weekly shop
goes on dairy versus meat versus fresh produce. Mad, right?

Then I realised that my wife's history wasn't included as she has her own More
card. Previously I'd have re-run all the code using her authentication tokens
and then merged somehow. Instead, I just asked Claude to make this
'multi-account' and again, hey presto, it just works.

So far so good, right?

### Where it went wrong

I'd got all my analytics ready and was happy as Larry - I shared with my wife
and told her to stop buying so much chocolate. But then we dug in because some
of the totals seemed off. Half of the products were misclassified. Rice pudding
was classified as rice. Pork and Ale sausages were misclassified as a drink.
Water chestnuts as a soft drink.

Had I been doing it myself, these are mistakes I wouldn't have made. It would
have been obvious because a clear step post-classification would have been to
examine some of the labels and check they were working. I didn't do that
because I didn't even know to do that - I just let Claude code go and off it
went.

Fortunately, I caught it and then embarked on a session of "let's check the
classification" but only really by accident. I've made similar mistakes before
- assuming part of the process has worked seamlessly, and not really realising
  how much rested on that assumption that I hadn't checked.

It's that lack of checking key assumptions, and the frightening speed and
obfuscation...just, the whole thing together means it's possible to move
quicker with LLMs than your understanding can keep up with. So you end up with
a project that's nominally _yours_ but that you don't deeply understand all
parts of.

It turns you into a project manager of a multi-faceted project...but you look
and feel like the developer. When somebody asks me about details of an
LLM-assisted project, I imagine I feel like a senior manager does when somebody
asks them about the work of their skip-level reports. It's probably OK because
they're generally good, but honestly...I'm not sure.

## Conclusion

Check out the project
[here](https://github.com/Kali89/morrisons-receipt-analytics) if you're
interested. But the more pressing conclusion is that I'm still learning how to
work effectively with LLMs and I don't think I've quite got the balance.
Ultimately I've probably got to accept going slower in order to ensure I understand and keep
ownership of my own projects. Lest I become the bumbling middle manager trying
to claim credit for my much smarter reports.
