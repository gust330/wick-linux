import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import St from 'gi://St';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';
import { Extension } from 'resource:///org/gnome/shell/extensions/extension.js';

const PRESETS = [
    { label: '30m', minutes: 30 },
    { label: '1h', minutes: 60 },
    { label: '2h', minutes: 120 },
    { label: '4h', minutes: 240 },
    { label: '8h', minutes: 480 },
    { label: '∞', minutes: 0 },
];

function formatClock(seconds) {
    const s = Math.max(0, Math.ceil(seconds));
    const hours = Math.floor(s / 3600);
    const minutes = Math.floor((s % 3600) / 60);
    const rest = s % 60;
    if (hours > 0) {
        return `${hours}:${String(minutes).padStart(2, '0')}:${String(rest).padStart(2, '0')}`;
    }
    return `${String(minutes).padStart(2, '0')}:${String(rest).padStart(2, '0')}`;
}

function formatCompact(seconds) {
    if (seconds < 60) return '<1m';
    const minutes = Math.ceil(seconds / 60);
    const hours = Math.floor(minutes / 60);
    const remMin = minutes % 60;
    if (hours > 0) {
        return `${hours}h ${String(remMin).padStart(2, '0')}m`;
    }
    return `${minutes}m`;
}

const WickIndicator = GObject.registerClass(
class WickIndicator extends PanelMenu.Button {
    _init(extensionPath) {
        super._init(0.0, 'Wick');
        this._path = extensionPath;
        this._selectedMinutes = 120; // Default 2h
        this._stopWhenAgentsFinish = true;

        // Top bar widget layout
        const topBox = new St.BoxLayout({
            style_class: 'panel-status-menu-box',
            reactive: true,
            can_focus: true,
            track_hover: true,
        });

        this._idleGicon = Gio.icon_new_for_string(`${this._path}/icons/wick-idle.svg`);
        this._awakeGicon = Gio.icon_new_for_string(`${this._path}/icons/wick-awake.svg`);

        this._icon = new St.Icon({
            gicon: this._idleGicon,
            icon_size: 16,
        });
        topBox.add_child(this._icon);

        this._topLabel = new St.Label({
            text: '',
            style_class: 'wick-topbar-label',
            y_align: Clutter.ActorAlign.CENTER,
            visible: false,
        });
        topBox.add_child(this._topLabel);

        this.add_child(topBox);

        this._buildMenu();
        this._updateState();

        this._timerId = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, 1, () => {
            this._updateState();
            return GLib.SOURCE_CONTINUE;
        });
    }

    _buildMenu() {
        const menuItem = new PopupMenu.PopupBaseMenuItem({
            reactive: false,
            can_focus: false,
        });
        this.menu.addMenuItem(menuItem);

        const container = new St.BoxLayout({
            vertical: true,
            style_class: 'wick-panel-box',
            x_expand: true,
        });
        menuItem.actor.add_child(container);

        // Status row
        const statusRow = new St.BoxLayout({
            vertical: false,
            style_class: 'wick-status-row',
            x_expand: true,
        });
        this._statusDot = new St.Widget({
            style_class: 'wick-dot-idle',
            y_align: Clutter.ActorAlign.CENTER,
        });
        this._statusText = new St.Label({
            text: 'Sleeps when the lid closes',
            style_class: 'wick-status-text',
            y_align: Clutter.ActorAlign.CENTER,
            x_expand: true,
        });
        statusRow.add_child(this._statusDot);
        statusRow.add_child(this._statusText);
        container.add_child(statusRow);

        // Hero row (Clock + Main Button)
        const heroRow = new St.BoxLayout({
            vertical: false,
            style_class: 'wick-hero-box',
            x_expand: true,
        });

        const clockBox = new St.BoxLayout({
            vertical: true,
            x_expand: true,
        });
        this._clockLabel = new St.Label({
            text: '2:00:00',
            style_class: 'wick-clock-label',
        });
        this._captionLabel = new St.Label({
            text: 'until you stop it',
            style_class: 'wick-caption-label',
        });
        clockBox.add_child(this._clockLabel);
        clockBox.add_child(this._captionLabel);
        heroRow.add_child(clockBox);

        this._mainBtn = new St.Button({
            label: '▶',
            style_class: 'wick-main-btn wick-main-btn-play',
            can_focus: true,
            y_align: Clutter.ActorAlign.CENTER,
        });
        this._mainBtn.connect('clicked', () => this._toggleSession());
        heroRow.add_child(this._mainBtn);
        container.add_child(heroRow);

        // Presets row
        const presetsRow = new St.BoxLayout({
            vertical: false,
            style_class: 'wick-presets-box',
            x_align: Clutter.ActorAlign.CENTER,
        });
        this._presetButtons = [];
        PRESETS.forEach(p => {
            const btn = new St.Button({
                label: p.label,
                style_class: 'wick-preset-btn' + (p.minutes === 120 ? ' wick-preset-selected' : ''),
                can_focus: true,
            });
            btn.connect('clicked', () => this._selectPreset(p.minutes, btn));
            presetsRow.add_child(btn);
            this._presetButtons.push({ btn, minutes: p.minutes });
        });
        container.add_child(presetsRow);

        // Conditions Card
        const card = new St.BoxLayout({
            vertical: true,
            style_class: 'wick-card',
        });

        // Agents row
        const agentBox = new St.BoxLayout({
            vertical: false,
            x_expand: true,
        });
        const agentLeft = new St.BoxLayout({
            vertical: true,
            x_expand: true,
        });
        const agentTitle = new St.Label({
            text: 'Stop when agents finish',
            style_class: 'wick-card-title',
        });
        this._agentDetail = new St.Label({
            text: 'Tracking active coding agents',
            style_class: 'wick-card-detail',
        });
        agentLeft.add_child(agentTitle);
        agentLeft.add_child(this._agentDetail);
        agentBox.add_child(agentLeft);

        this._agentSwitch = new St.Button({
            label: 'ON',
            style_class: 'wick-preset-btn wick-preset-selected',
            can_focus: true,
            y_align: Clutter.ActorAlign.CENTER,
        });
        this._agentSwitch.connect('clicked', () => {
            this._stopWhenAgentsFinish = !this._stopWhenAgentsFinish;
            this._agentSwitch.set_label(this._stopWhenAgentsFinish ? 'ON' : 'OFF');
        });
        agentBox.add_child(this._agentSwitch);
        card.add_child(agentBox);

        // Battery / Thermal telemetry row
        this._telemetryLabel = new St.Label({
            text: 'Battery: -- | Thermal: Normal',
            style_class: 'wick-card-detail',
            margin_top: 6,
        });
        card.add_child(this._telemetryLabel);

        container.add_child(card);
    }

    _selectPreset(minutes, btnActor) {
        this._selectedMinutes = minutes;
        this._presetButtons.forEach(p => {
            p.btn.remove_style_class_name('wick-preset-selected');
        });
        btnActor.add_style_class_name('wick-preset-selected');

        if (minutes === 0) {
            this._clockLabel.set_text('∞');
            this._captionLabel.set_text('until you stop it');
        } else {
            this._clockLabel.set_text(formatClock(minutes * 60));
            this._captionLabel.set_text(`for ${minutes}m`);
        }
    }

    _runWickCmd(args) {
        const binPath = `${GLib.get_home_dir()}/.local/bin/wick`;
        const cmd = [binPath, ...args];
        try {
            GLib.spawn_async(null, cmd, null, GLib.SpawnFlags.SEARCH_PATH, null);
        } catch (err) {
            logError(err, 'Failed to invoke wick binary');
        }
    }

    _toggleSession() {
        const state = this._readSession();
        if (state.isAwake) {
            this._runWickCmd(['off']);
        } else {
            const args = ['on'];
            if (this._selectedMinutes > 0) {
                args.push(`${this._selectedMinutes}m`);
            }
            if (this._stopWhenAgentsFinish) {
                args.push('--agents');
            }
            this._runWickCmd(args);
        }
        GLib.timeout_add(GLib.PRIORITY_DEFAULT, 300, () => {
            this._updateState();
            return GLib.SOURCE_REMOVE;
        });
    }

    _readSession() {
        const stateFile = `${GLib.get_home_dir()}/.local/state/wick/session.json`;
        try {
            if (GLib.file_test(stateFile, GLib.FileTest.EXISTS)) {
                const [ok, bytes] = GLib.file_get_contents(stateFile);
                if (ok) {
                    const text = new TextDecoder('utf-8').decode(bytes);
                    const json = JSON.parse(text);
                    return { isAwake: true, session: json };
                }
            }
        } catch (e) {
            // Ignore parse errors while writing
        }
        return { isAwake: false, session: null };
    }

    _updateState() {
        const { isAwake, session } = this._readSession();
        const now = Date.now();

        if (isAwake && session) {
            this._icon.set_gicon(this._awakeGicon);
            this._statusDot.style_class = 'wick-dot-awake';
            this._mainBtn.set_label('■');
            this._mainBtn.style_class = 'wick-main-btn wick-main-btn-stop';

            if (session.endsAt) {
                const endsAtMs = new Date(session.endsAt).getTime();
                const remSec = Math.max(0, (endsAtMs - now) / 1000);
                const clockText = formatClock(remSec);
                const compactText = formatCompact(remSec);

                this._clockLabel.set_text(clockText);
                this._captionLabel.set_text(`until ${new Date(endsAtMs).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`);
                this._statusText.set_text(`Awake with lid closed (${compactText} left)`);

                this._topLabel.set_text(compactText);
                this._topLabel.set_visible(true);
            } else {
                this._clockLabel.set_text('∞');
                this._captionLabel.set_text('until you stop it');
                this._statusText.set_text('Awake with the lid closed');
                this._topLabel.set_text('ON');
                this._topLabel.set_visible(true);
            }
        } else {
            this._icon.set_gicon(this._idleGicon);
            this._statusDot.style_class = 'wick-dot-idle';
            this._statusText.set_text('Sleeps when the lid closes');
            this._mainBtn.set_label('▶');
            this._mainBtn.style_class = 'wick-main-btn wick-main-btn-play';
            this._topLabel.set_visible(false);

            if (this._selectedMinutes === 0) {
                this._clockLabel.set_text('∞');
                this._captionLabel.set_text('until you stop it');
            } else {
                this._clockLabel.set_text(formatClock(this._selectedMinutes * 60));
                this._captionLabel.set_text(`for ${this._selectedMinutes}m`);
            }
        }

        // Read battery status from sysfs
        try {
            const batCapFile = '/sys/class/power_supply/BAT0/capacity';
            const batStatFile = '/sys/class/power_supply/BAT0/status';
            if (GLib.file_test(batCapFile, GLib.FileTest.EXISTS)) {
                const [cOk, cBytes] = GLib.file_get_contents(batCapFile);
                const [sOk, sBytes] = GLib.file_get_contents(batStatFile);
                if (cOk && sOk) {
                    const cap = new TextDecoder('utf-8').decode(cBytes).trim();
                    const st = new TextDecoder('utf-8').decode(sBytes).trim().toLowerCase();
                    this._telemetryLabel.set_text(`Battery: ${cap}% (${st}) | Floor: 20%`);
                }
            }
        } catch (e) {
            // Ignore telemetry errors
        }
    }

    destroy() {
        if (this._timerId) {
            GLib.source_remove(this._timerId);
            this._timerId = 0;
        }
        super.destroy();
    }
});

export default class WickExtension extends Extension {
    enable() {
        this._indicator = new WickIndicator(this.path);
        Main.panel.addToStatusArea(this.uuid, this._indicator);
    }

    disable() {
        if (this._indicator) {
            this._indicator.destroy();
            this._indicator = null;
        }
    }
}
