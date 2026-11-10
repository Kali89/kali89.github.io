---
layout: post
title: "Getting Real"
date: 2026-11-06
tags: [books, tech]
wordpress_id: 140
---

The latest in my run of techy book reviews --- this time an old classic:
[Getting Real](https://basecamp.com/gettingreal) by the team behind Basecamp.<!--more--> This too, has been doing the rounds at Automattic and has
been recommended by a colleague. Unlike the book on typography, this is
absolutely the kind of book I'd ordinarily read, and thus has stiffer
competition from the likes of The Lean Startup, Zero to One, and Hackers \&
Painters.

## Showing its age

The first thing that struck me about the book was that it feels dated. In the
early chapters, the authors present two alternatives: release versioned
software every few years on CD-ROMs, or release something every day (or at
least once a month) on a website. Maybe that advice would have hit differently
in 2006, but in 2026, it feels like it belongs in a museum.

Similarly, the companies and products that the book cites as bastions of wisdom
are underwhelming (though presumably were reasonable in their day). Launching
my company through specific named people's blogs, or taking advice on launching
from the person who deployed Microsoft's start.com (huh!?), or the idea of
using Yahoo as an internet leader....they all remind me of an internet that I
can only assume existed at some point, unfortunately before I had access to it.
(Note: I have to share this classic line: _"Which blogs listed at Technorati,
Blogdex, Feedster, Del.icio.us, and Daypop are hot on your trail?"_)

Finally, some of the tech advice is dated too. I don't even mean in the era of LLMs
(though of course, the idea that building things takes a long time now is
increasingly not true). The idea that you should focus first on the centre/meat
of the page, and only worry about the surrounding parts (navigation, footer)
later feels unusual, given that in pretty much all web development I've done
(usually with either Django or Rails), those elements come for free. Of course
you focus on the meat of the page, when the structure of your framework makes
anything else all but impossible.

## Showing its size

I've worked at companies of a variety of sizes. The smallest was probably
around 10-15 people (not counting my own start up), and the biggest was
around 150,000 (although in tech, I'd say Spotify hit around 8,000 while I was
there). The book is unashamedly focussed on small companies and start ups, and while it
says that these techniques can be used at larger companies, there was one part
that really led me to think that might not be the case.

The authors say that you should ideally _be_ the customer for whom you're
primarily developing, and that this will let you have real insight into what
real customers want. I agree with that wholeheartedly for small companies. The
advice to find a small group of people who love your product (rather than a
larger group of people who are OK with it) is great too, and forms a key part
of pretty much all the start up books I've read.

However, at some point, that has to stop. If you're trying to build a global
company with more than a billion users, your experience ceases to be the
be-all-and-end-all. You are no longer the target customer, or even anything
like the target customer.

Take Spotify for example. When Spotify was small, it was perfectly reasonable
for Daniel Ek to treat himself as its primary customer. At some point, though,
he will have arrived at a fork in the road. As a music lover and cataloguer,
there will be a feature that would improve the product for him, but would be
unnecessary for the average Spotify user. What should he do?

Mark Zuckerberg probably doesn't use Facebook to sell things on Marketplace. He
is no longer the customer. But for a time at Harvard, he was.

At some point, a product that has the ambition of being globally relevant has
to forego the idea that the founder (or staff) are the target market, and has
to undertake the effort of actually working out what customers think.
Politicians have to do the same. Perhaps to begin with, political instinct can
be found by considering one's own feelings. But if you're trying to make
national level inferences, you have to develop a way of understanding what the
nation thinks.

That's why, at a certain size/ambition level, companies tend to start hiring
people whose job this is. Once the staff are no longer the target customer,
they need some way of keeping in touch with those who are.

Whether or not the advice that a webpage ideally needs a team of three is
relevant any more is another matter of debate. A developer, a designer, and
somebody who can move between might reasonably be replaced now by "anybody, and
an LLM" but for a book this old, that's probably not worth going into. I do
like Amazon's two pizza rule (any team should be able to be fed with two large
pizzas) though. Maybe this predates that advice and was revolutionary in its
time (note: I looked it up and it
doesn't).

## Showing its lack of rigour

In comparison to The Lean Startup (which I think is the most
comparable book to this I've read), Getting Real feels deeply unscientific. The
authors themselves state that this book is going to be opinionated, loud, and
what worked for them. I think that's great, and of course managing a team of 5
people is wildly different from working in a team of thousands.

However, what I liked about The Lean Startup was that they presented _methods_
rather than just aphorisms. _"With web-based software there's no need to ship
perfection. Design screens, use them, analyze them, and then start over
again."_

OK...I don't disagree, but isn't that a little light? How should I analyze
them? How should I start over? Is this just telling me that I shouldn't aim to
make every screen perfect on the first try? How would I know if it was perfect?

Obviously my background in data is going to skew my perception here, and maybe
this was written before companies realised they had data that could be used in
this way, and perhaps Basecamp never got big enough to really do that kind of
data science work.

But having mostly worked for places that have, this feels light in
practical applicability.

## Showing its worth

There is plenty in this book that I agree with and think should be the
gold-standard for start ups (and for many other, bigger companies too).

- Work quickly and publicly
- Shipped is better than perfect
- Real is better than spec sheets (did people used to use those?)
- Build for yourself if possible, and if not, be incredibly close to your
    customer
- A few people loving you is better than a lot of people liking you
- Aim to build less
- Make opinionated software --- bloated software is almost always the result of
    trying to cater to too many people at once
- Feel free to ask users what you should build, but don't listen

For a book that's so heavily recommended at Automattic, there are also a
surprisingly large number of anti-patterns present in WordPress. Big versioned
releases every few months? Mounds of non-opinionated features that let (or
force) every user pick a different set of settings? That probably shows the
tension of a big project that grew to power so much of the web, and perhaps
this book shows the idealistic beginnings of that project. Maybe that's why the
book is recommended --- not as a statement of where we are, but as a reminder
of where we want to be. A call to managers and leaders to deliver pages, not
specs. To have opinions, launch quickly, and stick close to our users.

## Conclusion

Maybe I've been overly harsh, and perhaps this is the giant upon
whose shoulders later books stand. There are certainly lessons in here that I
think many software companies would do well to remember. Finding a small group
of people who love your product, and then launching as quickly as possible and
iterating on their feedback rapidly is absolutely the right idea. Resisting the
call of feature bloat, and focussing exclusively on a smaller set of things
that truly matter is critical as a company scales and takes on more demands.
Sticking close to the customer and offering unusually good customer service may
well be what takes you from 10,000 users to 100,000.

Ultimately though, I feel like I've read all of this advice in other, later books. Perhaps it was first, but others have done it better since. And
while a lot of this advice works well for a five-person company, I prefer my
advice to be more scalable, more battle-tested, and more rigorous.
