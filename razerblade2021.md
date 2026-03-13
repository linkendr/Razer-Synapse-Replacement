If your Razer Blade 14 is the 2021 model, the CPU is the AMD Ryzen 9 5900HX. It has 8 cores, 16 threads, a 3.3 GHz base clock, and up to 4.6 GHz max boost.
What it can do

That chip was the high-end AMD mobile processor in this model, and Razer positioned it as able to handle demanding AAA games and heavy programs smoothly while still being relatively efficient on battery for its class.​
In review coverage, the Blade 14’s 5900HX was described as faster than comparable Intel i7 options of the time and within about 5% of the best-performing 5900HX laptops tested.​
In practical terms, that means it is well suited for gaming, streaming while gaming, lots of browser tabs, coding, and moderately heavy creator work like photo editing or 1080p/1440p video editing.
What “Boost” means

On Razer Blade laptops, Synapse offers performance modes, and in Synapse 3 the Custom mode can set the CPU to “Boost.”​
Razer’s support guidance for low FPS also says to use Custom mode with “Boost” for CPU and “High” for GPU when you want maximum gaming performance, and it specifically says to do this while plugged into the original power adapter.​
So the Boost option is basically the aggressive performance profile: it lets the CPU prioritize higher clocks and power behavior for better speed, but it usually also means more heat, more fan noise, and worse battery life.
What to expect

For everyday use, you probably will not notice much difference between Balanced and Boost unless you are doing something CPU-heavy or gaming.
For games and heavier workloads, Boost can help the CPU stay more responsive and reduce bottlenecks, especially if the laptop is connected to power and the cooling is allowed to ramp up.
The 4.6 GHz figure is the chip’s max boost rating, not a speed you should expect to see locked on all cores all the time.
Best use

Use Balanced when you want less noise and better battery life, and use Boost when you want the most performance for gaming or heavier work.
A simple example: if you are playing a CPU-heavy game, compiling code, or rendering something, Boost makes sense; if you are just browsing, watching video, or doing office work, Balanced is usually the better choice.

If you want, I can also tell you what temperatures, clock speeds, and real-world performance are normal for the Blade 14 5900HX so you can check whether yours is running properly.
Prepared using GPT-5.4 Thinking
that laptop has a high mode for the GPU?

Yes — on the 2021 Razer Blade 14, the GPU does have a High setting in Custom mode.​
The CPU is the one that gets the separate “Boost” option, while the GPU options are low, medium, or high.​
How it works

The Blade 14’s performance modes are limited to Balanced and Custom, and inside Custom you can tune CPU and GPU performance separately.​
For maximum gaming performance, Razer’s support guidance says to use Custom mode with CPU set to Boost and GPU set to High, ideally while plugged into the original power adapter.​
So if you are looking at Synapse and wondering whether “High” is the top GPU setting on that model, the answer is yes.​

If you want, I can also explain what changes when you switch GPU from medium to high on the Blade 14, in plain terms like FPS, heat, and fan noise.
Prepared using GPT-5.4 Thinking
if you were to create custom software to replace synapse to have cpu boost and GPU high automatically kick in, what would be the best triggers to do so? what should you look for to automatically turn those features on and off?

Yes — if I were automating this on a 2021 Blade 14, I would make AC power and “real gaming/heavy app detected” the two main triggers, not raw clock speed alone.
The best controller would turn CPU Boost and GPU High on only when the laptop is plugged in and a demanding foreground app is clearly active, then turn them off for battery use, light workloads, or obvious heat/throttling situations.
Best triggers

Razer’s own guidance ties maximum-performance settings to being plugged into the original adapter, using Best performance in Windows, and selecting the high-performance NVIDIA path for games and apps.
So the strongest automatic “on” triggers are: charger connected, a known game or creator app in the foreground, Windows not in Battery Saver, and the app being assigned to the high-performance NVIDIA GPU.
On the Blade 14 specifically, I would also treat an external monitor as a stronger hint that the user wants performance, because reviews found external display use can improve FPS on this model.​
What to watch

Do not trigger from momentary clock spikes, because boost clocks are opportunistic and change constantly with load, power, and temperature.
Instead, watch sustained signals for 10 to 30 seconds: foreground process type, dGPU utilization, CPU package utilization, frame presentation activity, charger state, Battery Saver state, and whether the app is full-screen or borderless full-screen.
That lines up better with how Razer exposes these modes, which are broader performance profiles rather than simple fixed overclocks.
On and off logic

A good “turn on” rule would be: AC connected, Battery Saver off, game or heavy app detected, and either sustained dGPU load or sustained CPU-heavy foreground work.
A good “turn off” rule would be: charger unplugged, Battery Saver active, the heavy app closes or loses focus for a while, or the system shows persistent thermal stress instead of useful performance scaling.
I would also add hysteresis so it does not flap every few seconds, for example by requiring conditions to hold before switching on and requiring a cooldown period before switching back.
Best profile

For most people, the safest automatic policy would be three states: Balanced by default, CPU Boost plus GPU High only on AC with a real heavy workload, and immediate fallback to Balanced on battery.
I would not auto-enable max performance just because CPU or GPU usage briefly spikes, since browsers, launchers, and background tasks can do that without needing the noise, heat, and battery hit of the aggressive profile.
Because the Blade 14’s internal display does not have the same Advanced Optimus flexibility as some other Blade models, your app and power-source detection matter more than fancy display-mode logic here.
Practical rules

If you want a solid first version, I would use these triggers:

    Turn on Boost/High when AC is connected, Battery Saver is off, and a whitelisted game or heavy app is foregrounded.

    Also turn on when sustained dGPU load is high or when sustained CPU load is high in a creator or compile workload.

    Turn off when AC is removed, when the app exits or idles, or when the system is no longer getting meaningful benefit from the higher mode.

    Bias toward turning on sooner if an external monitor is attached.​

If you want, I can sketch an actual decision tree or pseudo-code for this auto-switcher.
Prepared using GPT-5.4 Thinking
I don't want to detect a program running as I don't want to curate by program, is there a way to detect usage load instead?

Yes — you can build this around usage load instead of a program whitelist, and that is probably the cleaner design for what you want. Razer’s own guidance already points to the important non-app signals: AC power state, battery-saving state, and whether the system is being pushed toward high-performance GPU use.
Best signals

The strongest inputs to watch are charger state, Battery Saver state, GPU load, GPU engine type, dedicated GPU memory use, and CPU load.
Windows can expose GPU usage, GPU engine, and dedicated/shared GPU memory in Task Manager because it pulls that data from WDDM’s GPU scheduler and memory manager, so these are reasonable telemetry sources for your own controller too.​
For the GPU, the most useful signal is not just “GPU %,” but whether the 3D engine is active, because Windows distinguishes 3D from things like video decode.​
What to trigger on

A good automatic “performance on” rule is: AC connected, Battery Saver off, and either sustained 3D GPU load or sustained heavy CPU load for a short window.
I would not trigger from a 1-second spike; I would require something like 10 to 20 seconds of sustained load before switching, because these modes are meant for real workload phases, not tiny bursts.
A practical first pass would be:

    Turn on CPU Boost + GPU High if AC is connected, Battery Saver is off, and GPU 3D engine stays above roughly 50 to 60 percent for 10 to 20 seconds.

    Also turn on if CPU utilization stays above roughly 70 to 80 percent for 15 to 30 seconds, even if GPU load is low.

    Bias more strongly toward “on” if dedicated GPU memory usage is climbing at the same time, because that usually means a real graphics workload rather than a trivial spike.​

What to ignore

Do not rely on total GPU % alone, because Windows reports the highest usage across GPU engines, so video playback or decode activity can look “busy” without meaning “needs max gaming mode.”​
That is why I would key mainly off the 3D engine plus dedicated VRAM use, not just the top-line GPU number.​
I would also force performance mode off on battery, because Razer explicitly notes battery operation is not equivalent to plugged-in performance and may even cap FPS unless battery-saving features are disabled.​
Turn-off logic

A good automatic “performance off” rule is: AC removed, Battery Saver enabled, or sustained low load after the heavy phase ends.
For example, switch back to Balanced if GPU 3D load falls below about 20 percent and CPU falls below about 35 to 40 percent for 30 to 60 seconds.
I would also add a minimum hold time, such as “stay in performance mode for at least 2 to 5 minutes once enabled,” so the mode does not flap during menus, loading screens, or short scene changes.
Recommended design

If I were writing it, I would use a weighted score instead of one single threshold:

    +3 if AC connected.

    +3 if Battery Saver is off.​

    +4 if GPU 3D engine is sustained high.​

    +2 if dedicated GPU memory is above a chosen threshold.​

    +3 if CPU load is sustained high.

    Switch to Boost/High when score crosses the “on” threshold, and switch back only when it drops well below a lower “off” threshold.

That approach is better than a whitelist because it reacts to actual behavior, and better than raw clock watching because clocks are opportunistic while utilization, GPU engine type, power state, and battery-saving state reflect the real workload more directly.

If you want, I can sketch a concrete Windows implementation plan next — for example, which APIs/counters to read and a simple state machine for your Blade 14.
Prepared using GPT-5.4 Thinking
I want 3 phases, boost on, boost off, automatic. can you design me the triggers for the automatic mode?

Yes — for your 3-phase design, I would make Auto mode a small state machine with two hard gates first: performance mode should only be eligible when the laptop is on AC power, and it should immediately back off when battery-saving behavior is active. Razer explicitly ties best gaming performance to being plugged in, and it notes that battery-saving features can cap performance and are still not equivalent to plugged-in operation.
Core rule

Use three modes: On = force CPU Boost + GPU High, Off = force Balanced, Auto = load-driven switching with hysteresis. For Auto, use system telemetry instead of app detection, and key mainly off the GPU’s 3D engine plus CPU load, because Windows exposes GPU usage and the specific GPU engine in Task Manager data.
Enter Boost

I would require these hard conditions before Auto can enable Boost/High:

    AC connected.

    Battery Saver off, and if you use GeForce Experience, Battery Boost off.​

    Then trigger on sustained load, not spikes.

Recommended “turn on” triggers:

    GPU 3D engine average >= 55% for 15 seconds.

    Or GPU 3D engine >= 35% and dedicated GPU memory >= 1.5 GB for 15 seconds.

    Or CPU average >= 80% for 20 seconds.

    Fast path: GPU 3D engine >= 85% for 5 seconds.

That design matches the telemetry Windows exposes: the GPU Engine field lets you distinguish 3D work from things like video decode, and the plain GPU % alone can be misleading because it reports the busiest engine rather than “gaming load” specifically.
Exit Boost

I would make the “turn off” side slower than the “turn on” side:

    Immediate off if AC is disconnected.

    Immediate off if Battery Saver turns on.​

    Otherwise step back only when load stays low for a while.

Recommended “turn off” triggers:

    GPU 3D engine <= 15% and CPU <= 35% for 60 seconds.

    Or GPU 3D engine <= 25% and dedicated GPU memory <= 700 MB for 60 seconds.

    Optional battery guard: if battery drops below a threshold you choose, force Off until AC returns.

Stability rules

Add hysteresis so it does not flap in menus, loading screens, or alt-tab moments. I would use a minimum on-time of 3 minutes after entering Boost, plus a minimum off-time of 30 to 45 seconds before it can re-enter.
Also sample once per second but make decisions from rolling averages, for example 15-second and 60-second windows.
Practical design

If I were implementing Auto, I would use this exact logic:

    If mode = On, force CPU Boost + GPU High.

    If mode = Off, force Balanced.

    If mode = Auto:

    If AC is not connected, force Balanced.

    Else if Battery Saver or Battery Boost is active, force Balanced.​

    Else if fast-path or sustained-load triggers are met, enable CPU Boost + GPU High.

    Else if low-load exit conditions are met for 60 seconds, return to Balanced.

    Else keep current state.

If you want, I can turn this into actual pseudo-code or a Windows service design using the exact counters to read for CPU load, GPU 3D engine, and VRAM.