'use strict';

function deferTransition(current, requested, unchanged) {
    return !unchanged && Number.isInteger(current) && current > 0 && current <= 0xb800
        && Number.isInteger(requested) && requested >= 0 && requested + 0x80 > 0xb800;
}

if (typeof Process === 'undefined') {
    module.exports = {deferTransition};
} else {
    const executable = Process.getModuleByName('survarium.exe');
    const signatures = [
        [0x561ac0, '4c894c24204489442418555657415441'],
        [0x57c760, '40554883ec20488d6c2420488b453048'],
        [0x2b51c0, '48895c240848896c2410488974241848897c242041564883ec304c8b5948468d'],
        [0x2b5f27, 'e894f2ffff'],
        [0x2b5f65, 'e856f2ffff']
    ];
    for (const [offset, expected] of signatures) {
        const actual = Array.from(new Uint8Array(executable.base.add(offset).readByteArray(expected.length / 2)),
                                  value => value.toString(16).padStart(2, '0')).join('');
        if (actual !== expected) throw new Error('Unsupported animation function at ' + offset.toString(16));
    }
    const mixers = new Map();
    const observers = [];
    const trampolines = [];
    globalThis.animationGuardMemory = {observers, trampolines};
    let deferred = 0;
    let errors = 0;
    const report = error => {
        if (++errors <= 3) send({event: 'animation_guard_error', error: String(error)});
    };
    observers.push(Interceptor.attach(executable.base.add(0x561ac0), {
        onEnter(args) {
            this.previous = mixers.get(this.threadId);
            mixers.delete(this.threadId);
            try {
                const tree = args[0].add(0x17180).readPointer();
                if (!tree.isNull()) mixers.set(this.threadId, tree.sub(4).readU32());
            } catch (error) { report(error); }
        },
        onLeave() {
            if (this.previous === undefined) mixers.delete(this.threadId);
            else mixers.set(this.threadId, this.previous);
        }
    }));
    observers.push(Interceptor.attach(executable.base.add(0x57c760), {
        onEnter(args) {
            this.plan = args[0];
            this.capacity = mixers.get(this.threadId);
            this.expectedCaller = this.returnAddress.equals(executable.base.add(0x561dab));
        },
        onLeave() {
            if (!this.expectedCaller || this.capacity === undefined) return;
            try {
                const requested = this.plan.add(0x30).readU32();
                if (deferTransition(this.capacity, requested, this.plan.add(0x38).readU8() !== 0)) {
                    this.plan.add(0x38).writeU8(1);
                    deferred++;
                    if (deferred <= 10 || deferred % 500 === 0)
                        send({event: 'animation_transition_deferred', requested: requested + 0x80, count: deferred});
                }
            } catch (error) { report(error); }
        }
    }));
    // These two callers can request entry zero from a one-based animation table.
    for (const offset of [0x2b5f27, 0x2b5f65]) {
        const site = executable.base.add(offset);
        const stub = Memory.alloc(Process.pageSize, {near: site, maxDistance: 0x7fffffff});
        trampolines.push(stub);
        Memory.patchCode(stub, 128, writable => {
            const writer = new X86Writer(writable, {pc: stub});
            writer.putTestRegReg('r9d', 'r9d');
            writer.putJccShortLabel('je', 'resume', 'no-hint');
            writer.putCallAddress(executable.base.add(0x2b51c0));
            writer.putLabel('resume');
            writer.putJmpAddress(site.add(5));
            writer.flush();
        });
        Memory.patchCode(site, 5, writable => {
            const writer = new X86Writer(writable, {pc: site});
            writer.putJmpAddress(stub);
            writer.flush();
            if (writer.offset !== 5) throw new Error('Animation trampoline is outside branch range');
        });
    }
    Interceptor.flush();
    send({event: 'animation_guard_ready', capacity: 0xb800, hooks: observers.length, zero_index_sites: trampolines.length});
}
