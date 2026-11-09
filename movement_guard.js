'use strict';

function preserveSmallStep(deltaMs, accumulator, fixed) {
    return Number.isInteger(deltaMs) && deltaMs > 0 && deltaMs < 10
        && Number.isFinite(accumulator) && accumulator >= 0 && accumulator < fixed;
}

function compatibleCapsule(stand, crouch, height, lowHeight) {
    return Math.abs(stand - .76) < 1e-6 && Math.abs(crouch - .76) < 1e-6
        && Math.abs(height - 1.8) < 1e-6 && Math.abs(lowHeight - 1.1) < 1e-6;
}

if (typeof Process === 'undefined') {
    module.exports = {preserveSmallStep, compatibleCapsule};
} else {
    const base = Process.getModuleByName('survarium.exe').base;
    const signatures = [
        [0x5f5dcc, '450f57e4'], [0x5f3bd0, '0f57f6'],
        [0x5f3f32, '0f2f95a0000000732f'],
        [0x5f5ea5, '440f2f55700f8308020000'], [0x5f61b7, '440f2f5570732c'],
        [0x41558e, 'c74710ffffffffc7471801000000'],
        [0x40043d, '0f2fc276250f2ffef30f1197a80000000f28c277074489bfac000000'],
        [0x40052c, '488d0ddd216f00e838e6c8ff418bcf2bcb3bc80f82c9010000'],
        [0x5e7340, '48895c2408574883ec20488b81d0c60100488bd9f30f101d94e83f000f57c98bfa448980e80000004533c0488b89d0c60100488b01ff5058488b8bd0c601000f57c9f30f101d5ae83f0041b80a000000f3480f2acf4c8b09f30f5e0d44ed3f00488b5c24304883c4205f49ff6158'],
        [0x5f6e90, '488b41304885c074664883b8d0c60100'],
        [0x2fda80, '488bc448895810488970184889782055488da8a8']
    ];
    for (const [offset, expected] of signatures) {
        const bytes = new Uint8Array(base.add(offset).readByteArray(expected.length / 2));
        if (Array.from(bytes, value => value.toString(16).padStart(2, '0')).join('') !== expected)
            throw new Error('Unsupported movement code at ' + offset.toString(16));
    }
    const fixed = base.add(0x9e5be4).readFloat();
    if (Math.abs(fixed - .01) > 1e-8 || base.add(0x9e60e4).readFloat() !== 1000)
        throw new Error('Unexpected native physics time units');
    const loads = [[0x5f4194, 8], [0x5f44cf, 8], [0x5f47a4, 8],
                   [0x5f5111, 9], [0x5f54f4, 9], [0x5f4f83, 8]];
    for (const [offset, size] of loads) {
        const site = base.add(offset);
        const code = Array.from(new Uint8Array(site.readByteArray(size)));
        const prefix = size === 8 ? [0xf3, 0x0f, 0x10, 0x05]
                                  : [0xf3, 0x44, 0x0f, 0x10, offset === 0x5f54f4 ? 0x25 : 0x1d];
        if (!prefix.every((value, index) => code[index] === value)
                || !site.add(size).add(site.add(size - 4).readS32()).equals(base.add(0x9e5ba8)))
            throw new Error('Unsupported displacement threshold at ' + offset.toString(16));
    }
    const threshold = Memory.alloc(Process.pageSize, {near: base.add(loads[0][0]), maxDistance: 0x7fffffff});
    threshold.writeFloat(1e-10);
    for (const [offset, size] of loads) {
        const target = base.add(offset + size);
        const relative = threshold.sub(target).toInt32();
        if (!target.add(relative).equals(threshold)) throw new Error('Movement threshold is outside branch range');
    }
    const hooks = [];
    globalThis.movementGuardMemory = {threshold, hooks};
    for (const [offset, size] of loads) {
        const site = base.add(offset);
        const relative = threshold.sub(site.add(size)).toInt32();
        Memory.patchCode(site.add(size - 4), 4, writable => writable.writeS32(relative));
    }
    for (const offset of [0x5f5ea5, 0x5f61b7])
        Memory.patchCode(base.add(offset + 3), 1, writable => writable.writeU8(0x65));
    Memory.patchCode(base.add(0x5f3f34), 1, writable => writable.writeU8(0xb5));
    Memory.patchCode(base.add(0x41558e), 7, writable => writable.writeByteArray([0x44, 0x89, 0x7f, 0x10, 0x90, 0x90, 0x90]));
    Memory.patchCode(base.add(0x400450), 2, writable => writable.writeByteArray([0x90, 0x90]));
    Memory.patchCode(base.add(0x400533), 5, writable => writable.writeByteArray([0xb8, 0x88, 0x13, 0x00, 0x00]));
    let preserved = 0;
    let steps = 0;
    let gravityCorrections = 0;
    let capsules = 0;
    hooks.push(Interceptor.attach(base.add(0x675230), {
        onEnter(args) {
            this.accumulator = null;
            this.countSteps = args[2].toInt32() === 10;
            if (!this.returnAddress.equals(base.add(0x5e7378)) || args[2].toInt32() !== 0) return;
            const address = args[0].add(0x150);
            const value = address.readFloat();
            if (preserveSmallStep(this.context.rdi.toUInt32(), value, fixed)) {
                this.accumulator = address;
                this.value = value;
            }
        },
        onLeave(result) {
            if (this.accumulator !== null) {
                this.accumulator.writeFloat(this.value);
                preserved++;
            }
            if (this.countSteps) steps += result.toInt32();
        }
    }));
    hooks.push(Interceptor.attach(base.add(0x5f6e90), {
        onEnter(args) {
            this.smallStep = false;
            if (!this.returnAddress.equals(base.add(0x5f3b87))) return;
            const step = args[0].add(0x6124).readFloat();
            const vertical = args[0].add(0x61a4).readFloat();
            this.smallStep = step > 0 && step < .0095 && Number.isFinite(vertical) && vertical <= 0;
        },
        onLeave(result) {
            if (this.smallStep && (result.toUInt32() & 255) === 1) {
                result.replace(0);
                gravityCorrections++;
            }
        }
    }));
    hooks.push(Interceptor.attach(base.add(0x2fda80), {
        onEnter(args) { this.settings = args[0]; },
        onLeave() {
            const settings = this.settings;
            if (!compatibleCapsule(settings.add(0x408).readFloat(), settings.add(0x410).readFloat(),
                                   settings.add(0x40c).readFloat(), settings.add(0x414).readFloat())) return;
            settings.add(0x408).writeFloat(.70);
            settings.add(0x410).writeFloat(.70);
            capsules++;
        }
    }));
    const timer = setInterval(() => {
        if (steps || preserved || gravityCorrections || capsules)
            send({event: 'movement_physics', steps, preserved, gravityCorrections, capsules});
        steps = preserved = gravityCorrections = capsules = 0;
    }, 5000);
    globalThis.movementGuardMemory.timer = timer;
    Interceptor.flush();
    send({event: 'movement_guard_ready', smallDisplacementSites: loads.length,
          fixedPhysicsSeconds: fixed, squaredThreshold: threshold.readFloat(), characterDiameter: .70});
}
