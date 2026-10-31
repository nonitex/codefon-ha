// The Kaputelefon panel of the Codefon integration: talk with the gate
// caller from any device Home Assistant opens on (Nabu Casa too). The audio
// worklet (line cleaner, resampling, push-to-talk) is the one of the logger's
// /tavoli page (firmware/web.cpp); keep the two alike.
const WORKLET = `// Line audio cleaner at 8333 Sa/s: notches on the steady tones from the gate
// side (1 kHz and 1250 Hz families), then a Wiener noise suppressor
// (256-point STFT, decision-directed SNR, noise from minimum tracking).
class Clean{constructor(){const fs=8333.333;this.bq=[];
for(const f0 of [1000,1250,2000,2500,3000,3750,4000]){const q=f0==1250?12:25,w=2*Math.PI*f0/fs,al=Math.sin(w)/(2*q),c=Math.cos(w),a0=1+al;
this.bq.push([1/a0,-2*c/a0,1/a0,-2*c/a0,(1-al)/a0,0,0,0,0])}
const N=256;this.N=N;this.h=N/2;this.w=new Float32Array(N);for(let i=0;i<N;i++)this.w[i]=Math.sqrt(0.5-0.5*Math.cos(2*Math.PI*i/N));
this.inb=new Float32Array(N);this.ob=new Float32Array(N);this.oq=new Float32Array(N/2);this.fill=0;this.re=new Float32Array(N);this.im=new Float32Array(N);
const K=N/2+1;this.ps=new Float32Array(K);this.nz=new Float32Array(K).fill(1e9);this.pg=new Float32Array(K).fill(1);this.pp=new Float32Array(K);
this.fr=0;this.on=true}
fft(re,im,inv){const n=re.length;for(let i=1,j=0;i<n;i++){let b=n>>1;for(;j&b;b>>=1)j^=b;j^=b;
if(i<j){let t=re[i];re[i]=re[j];re[j]=t;t=im[i];im[i]=im[j];im[j]=t}}
for(let l=2;l<=n;l<<=1){const a=(inv?2:-2)*Math.PI/l,wr=Math.cos(a),wi=Math.sin(a);
for(let i=0;i<n;i+=l){let cr=1,ci=0;for(let k=0;k<l/2;k++){const p=i+k,q=p+l/2,tr=re[q]*cr-im[q]*ci,ti=re[q]*ci+im[q]*cr;
re[q]=re[p]-tr;im[q]=im[p]-ti;re[p]+=tr;im[p]+=ti;const t=cr*wr-ci*wi;ci=cr*wi+ci*wr;cr=t}}}}
frame(){const N=this.N,K=N/2+1,re=this.re,im=this.im;for(let i=0;i<N;i++){re[i]=this.inb[i]*this.w[i];im[i]=0}
this.fft(re,im,false);this.fr++;
for(let k=0;k<K;k++){const p=re[k]*re[k]+im[k]*im[k];this.ps[k]=this.fr==1?p:0.7*this.ps[k]+0.3*p;
const s=this.ps[k];this.nz[k]=s<this.nz[k]?s:this.nz[k]*1.003;const nb=1.6*this.nz[k]+1e-12;
const post=p/nb,prio=0.97*this.pg[k]*this.pg[k]*this.pp[k]/nb+0.03*Math.max(post-1,0);
let g=prio/(1+prio);if(g<0.12)g=0.12;if(!this.on)g=1;this.pg[k]=g;this.pp[k]=p;
re[k]*=g;im[k]*=g;if(k>0&&k<N/2){re[N-k]=re[k];im[N-k]=-im[k]}}
this.fft(re,im,true);for(let i=0;i<N;i++)this.ob[i]+=re[i]/N*this.w[i]}
// One sample in, one out (N samples later).
step(x){for(const b of this.bq){const y=b[0]*x+b[1]*b[5]+b[2]*b[6]-b[3]*b[7]-b[4]*b[8];b[6]=b[5];b[5]=x;b[8]=b[7];b[7]=y;x=y}
const h=this.h,out=this.oq[this.fill];this.inb[h+this.fill]=x;
if(++this.fill==h){this.frame();this.oq.set(this.ob.subarray(0,h));this.inb.copyWithin(0,h);this.ob.copyWithin(0,h);this.ob.fill(0,h);this.fill=0}
return out}}
class V extends AudioWorkletProcessor{constructor(){super();this.cl=new Clean();this.ptt=false;this.st=8333.333/sampleRate;
this.ip=0;this.prev=0;this.b=new Int16Array(160);this.n=0;this.q=new Float32Array(16384);this.qr=0;this.qw=0;
this.pr=false;this.op=0;this.a=0;this.c=0;this.env=0.001;this.es=0;this.nf=0.01;this.gt=1;this.vol=0.5;this.pt=0;this.pk=0;this.k=0;
this.port.onmessage=e=>{const d=e.data;if('ptt' in d){this.ptt=d.ptt;this.n=0}if('vol' in d)this.vol=d.vol;if('ns' in d)this.cl.on=d.ns;
if(d.rx){const a=d.rx;for(let i=0;i<a.length;i++){this.q[this.qw&16383]=this.cl.step(a[i]/32768);this.qw++}
if(this.qw-this.qr>6000)this.qr=this.qw-1600}}}
process(I,O){const x=I[0]&&I[0][0],o=O[0][0];
if(this.ptt&&x){for(let i=0;i<x.length;i++){this.ip+=this.st;if(this.ip>=1){this.ip-=1;
const y=this.prev+(x[i]-this.prev)*(1-this.ip/this.st);const v=Math.max(-1,Math.min(1,y));
this.pt=Math.max(this.pt,Math.abs(v));this.b[this.n++]=v*32767;if(this.n==160){this.port.postMessage({tx:this.b.slice()});this.n=0}}
this.prev=x[i]}}
for(let i=0;i<o.length;i++){if(this.ptt){o[i]=0;continue}this.op+=this.st;if(this.op>=1){this.op-=1;this.a=this.c;
if(!this.pr&&this.qw-this.qr>=1600)this.pr=true;if(this.pr&&this.qr<this.qw){this.c=this.q[this.qr&16383];this.qr++}
else{this.pr=false;this.c*=0.9}const m=Math.abs(this.c);this.env=Math.max(m,this.env*0.9997);
this.es+=(m-this.es)*0.01;this.nf=Math.min(Math.max(this.es,1e-5),this.nf*1.00005);
const open=this.es>3*this.nf;this.gt+=((open?1:0.2)-this.gt)*(open?0.02:0.0005)}
const g=Math.min(120,0.3/(this.env+1e-6))*this.vol*this.gt;const v=Math.max(-1,Math.min(1,(this.a+(this.c-this.a)*this.op)*g));
o[i]=v;this.pk=Math.max(this.pk,Math.abs(v))}
if(++this.k>=12){this.k=0;this.port.postMessage({mt:this.pt,mr:this.pk});this.pt=0;this.pk=0}return true}}
registerProcessor('v',V)`;

const CSS = `
:host{display:block;padding:16px;max-width:640px;margin:0 auto;color:var(--primary-text-color);font-family:var(--paper-font-body1_-_font-family,sans-serif)}
.card{background:var(--card-background-color,#fff);border-radius:12px;padding:16px;margin-bottom:12px;box-shadow:var(--ha-card-box-shadow,0 1px 3px rgba(0,0,0,.2))}
h1{font-size:1.4rem;margin:0 0 8px}
.st{color:var(--secondary-text-color)}.st.bad{color:var(--error-color,#c00)}
.call{font-size:1.3rem;font-weight:bold;margin:8px 0}.call.ring{color:var(--warning-color,#e65100);animation:b 1s infinite}
@keyframes b{50%{opacity:.4}}
button{font:inherit;border:0;border-radius:10px;padding:12px 16px;margin:4px 4px 4px 0;background:var(--primary-color,#03a9f4);color:var(--text-primary-color,#fff);cursor:pointer}
button:disabled{opacity:.35;cursor:default}
#go{width:100%;font-size:1.2rem}
#ptt{width:100%;height:9rem;font-size:1.5rem;margin-top:8px;touch-action:none;user-select:none;-webkit-user-select:none}
#ptt.on{background:var(--error-color,#c62828)}
#door{background:var(--warning-color,#ef6c00)}
.m{height:8px;background:var(--divider-color,#ddd);border-radius:4px;overflow:hidden;margin:4px 0 10px}.m div{height:100%;width:0;background:var(--primary-color,#03a9f4)}
label{display:block;margin:8px 0}input[type=range]{width:100%}
.msg{min-height:1.2em;color:var(--secondary-text-color)}
a{color:var(--primary-color)}
`;

const HTML = `
<div class="card"><h1>Kaputelefon</h1>
<div class="st" id="st">Kapcsolódás…</div>
<div id="secure"></div>
<button id="go">Hang bekapcsolása</button>
<div class="call" id="call"></div>
<div><button id="up" disabled>Felvétel</button><button id="down" disabled>Letevés</button><button id="door" disabled>Ajtónyitás</button></div>
<div class="msg" id="msg"></div>
<button id="ptt" disabled>Nyomd és beszélj</button>
</div>
<div class="card">
<div>Kimenő hang</div><div class="m"><div id="mt"></div></div>
<div>A vonal (a hívó)</div><div class="m"><div id="mr"></div></div>
<label>Hallgatás hangereje<input id="rv" type="range" min="0" max="100" value="70"></label>
<label>Adás erőssége<input id="tv" type="range" min="0" max="100" value="50"></label>
<label><input id="ns" type="checkbox" checked> Zajszűrés (alapzaj és csipogás)</label>
</div>`;

const ERR_TEXT = {busy: 'Foglalt.', unreachable: 'A naplózó nem érhető el.'};

class CodefonPanel extends HTMLElement {
  set hass(h) { this._hass = h; if (!this._built) this._build(); }
  get hass() { return this._hass; }

  _build() {
    this._built = true;
    const root = this.attachShadow({mode: 'open'});
    root.innerHTML = `<style>${CSS}</style>${HTML}`;
    this.$ = id => root.getElementById(id);
    this.ws = null; this.ctx = null; this.node = null; this.txg = null;
    this.down = false; this.may = false; this.ring = false; this.talk = false;
    this.hello = null; this.state = {state: 'idle'}; this.cid = 0; this.seq = 0; this.lastBeep = 0;
    this.tries = 0; this.listening = false;
    this.autoUp = /[?&]hivas=1/.test(location.search);
    if (this.autoUp) this.$('go').textContent = 'Felvétel és hang';
    this._load();
    // The connection needs no tap; the browser gives sound and the
    // microphone only after one, so the first of these taps starts them.
    this.$('go').onclick = async () => { if (await this._audio() && this.autoUp && this.ring) { this.autoUp = false; this._cmd('up'); } };
    this.$('up').onclick = async () => { await this._audio(); this._cmd('up'); };
    this.$('down').onclick = () => this._cmd('down');
    this.$('door').onclick = () => this._cmd('door');
    const P = this.$('ptt');
    P.addEventListener('pointerdown', async e => {
      e.preventDefault(); P.setPointerCapture(e.pointerId); this.held = true;
      if (!this.node && !(await this._audio())) return;
      if (this.held) this._ptt(true);
    });
    ['pointerup', 'pointercancel'].forEach(t => P.addEventListener(t, () => { this.held = false; this._ptt(false); }));
    P.addEventListener('contextmenu', e => e.preventDefault());
    ['rv', 'tv'].forEach(i => {
      try { const v = localStorage.getItem('codefon.' + i); if (v !== null) this.$(i).value = v; } catch (e) {}
      this.$(i).oninput = () => { this._vol(); try { localStorage.setItem('codefon.' + i, this.$(i).value); } catch (e) {} };
    });
    try { this.$('ns').checked = localStorage.getItem('codefon.ns') !== '0'; } catch (e) {}
    this.$('ns').onchange = () => { this._vol(); try { localStorage.setItem('codefon.ns', this.$('ns').checked ? '1' : '0'); } catch (e) {} };
    document.addEventListener('visibilitychange', async () => {
      if (document.visibilityState !== 'visible' || !this.ctx) return;
      try { this.lock = await navigator.wakeLock.request('screen'); } catch (e) {}
      if (this.ctx.state !== 'running') this.ctx.resume();
      if (!this.ws) { clearTimeout(this.retry); this._connect(); }
    });
  }

  async _load() {
    try {
      const r = await this._hass.callWS({type: 'codefon/list'});
      this.devices = r.devices;
      this.secureUrl = r.secure_url;
      if (!r.devices.length) { this._status('Nincs beállított Codefon naplózó.', true); this.$('go').disabled = true; return; }
      this.device = r.devices[0];
    } catch (e) { this._status('A Codefon integráció nem válaszol: ' + e.message, true); return; }
    this._connect();
    if (!window.isSecureContext) {
      this.insecure = true;
      this.$('go').disabled = true;
      if (this.secureUrl) {
        const u = this.secureUrl.replace(/\/$/, '') + '/kaputelefon' + location.search;
        this.$('secure').innerHTML = `<p><a href="${u}">Megnyitás a HTTPS címen</a></p>`;
      } else {
        this.$('secure').innerHTML = '<p>A Home Assistantnak nincs HTTPS címe (Nabu Casa vagy saját domain).</p>';
      }
    }
  }

  _okText() {
    return this.insecure ? 'Kapcsolat megvan. Hang csak HTTPS címen van, a gombok így is működnek.'
      : this.node ? 'Kapcsolat megvan.' : 'Kapcsolat megvan. A hang az első koppintással indul.';
  }

  _status(t, bad) { const s = this.$('st'); s.textContent = t; s.classList.toggle('bad', !!bad); }

  // Starts sound and the microphone (needs a tap); true once they run.
  async _audio() {
    if (this.node) return true;
    if (this.starting) return this.starting;
    this.starting = this._startAudio();
    const ok = await this.starting;
    this.starting = null;
    return ok;
  }

  async _startAudio() {
    if (this.insecure) { this.$('msg').textContent = 'Hang csak HTTPS címen van (lásd fent).'; return false; }
    this.$('go').disabled = true;
    try {
      this.ctx = new AudioContext({latencyHint: 'interactive'});
      await this.ctx.audioWorklet.addModule(URL.createObjectURL(new Blob([WORKLET], {type: 'text/javascript'})));
      const mic = await navigator.mediaDevices.getUserMedia({audio: {echoCancellation: true, noiseSuppression: true, autoGainControl: true}});
      const c = this.ctx, src = c.createMediaStreamSource(mic);
      const hp = new BiquadFilterNode(c, {type: 'highpass', frequency: 300});
      const l1 = new BiquadFilterNode(c, {type: 'lowpass', frequency: 3300}), l2 = new BiquadFilterNode(c, {type: 'lowpass', frequency: 3300});
      const cp = new DynamicsCompressorNode(c, {threshold: -40, knee: 10, ratio: 8, attack: 0.003, release: 0.25});
      this.txg = new GainNode(c);
      this.node = new AudioWorkletNode(c, 'v', {numberOfInputs: 1, numberOfOutputs: 1, outputChannelCount: [1]});
      src.connect(hp).connect(l1).connect(l2).connect(cp).connect(this.txg).connect(this.node);
      this.node.connect(new BiquadFilterNode(c, {type: 'highpass', frequency: 200}))
        .connect(new BiquadFilterNode(c, {type: 'lowpass', frequency: 3400}))
        .connect(new BiquadFilterNode(c, {type: 'lowpass', frequency: 3400})).connect(c.destination);
      this.node.port.onmessage = e => {
        const d = e.data;
        if (d.tx) { if (this.down) this._sendTx(d.tx); }
        else { this.$('mt').style.width = Math.min(100, d.mt * 100) + '%'; this.$('mr').style.width = Math.min(100, d.mr * 100) + '%'; }
      };
      this._vol();
      await c.resume();
      this._status(this._okText());
      try { this.lock = await navigator.wakeLock.request('screen'); } catch (e) {}
      this.$('go').hidden = true;
      return true;
    } catch (e) {
      this.node = null;
      this.$('msg').textContent = 'A hang nem indult: ' + e.message;
      this.$('go').disabled = false;
      return false;
    }
  }

  _vol() {
    if (this.node) this.node.port.postMessage({vol: Math.pow(this.$('rv').value / 100, 2), ns: this.$('ns').checked});
    if (this.txg) this.txg.gain.value = this.$('tv').value / 25;
  }

  async _connect() {
    clearTimeout(this.retry);
    this._status(this.tries ? `Újrakapcsolódás (${this.tries}. próba)…` : 'Kapcsolódás…');
    let path;
    try {
      path = (await this._hass.callWS({type: 'auth/sign_path', path: `/api/codefon/ws/${this.device.entry_id}`, expires: 30})).path;
    } catch (e) { this._drop(); return; }
    const ws = new WebSocket((location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + path);
    ws.binaryType = 'arraybuffer';
    this.ws = ws;
    ws.onopen = () => { this.tries = 0; this._status(this._okText()); };
    ws.onclose = () => { if (this.ws === ws) this._drop(); };
    ws.onmessage = e => {
      if (typeof e.data !== 'string') {
        if (this.node) this.node.port.postMessage({rx: new Int16Array(e.data, 4)});
        return;
      }
      const j = JSON.parse(e.data);
      if (j.t === 'hello') { this.hello = j; this._show(); }
      else if (j.t === 'state') { this.state = j; this._show(); }
      else if (j.t === 'connection') { if (!j.connected) this._status('A naplózó nem érhető el, a Home Assistant újrakapcsolódik…', true); else this._status(this._okText()); }
      else if (j.t === 'audio') { if (!j.talk && this.down) { this._ptt(false); this.$('msg').textContent = 'Az adás véget ért.'; } if (!j.listen) this.listening = false; }
      else if (j.t === 'reply') this._reply(j);
      else if (j.t === 'event') this._event(j);
    };
  }

  _drop() {
    if (this.ws) { this.ws.onclose = this.ws.onmessage = null; try { this.ws.close(); } catch (e) {} this.ws = null; }
    if (this.down) this._ptt(false);
    this.listening = false; this.may = false; this.ring = this.talk = false;
    ['up', 'down', 'door', 'ptt'].forEach(b => this.$(b).disabled = true);
    this._status('A kapcsolat megszakadt, újra…', true);
    this.tries++;
    this.retry = setTimeout(() => this._connect(), 2000);
  }

  _flatOk(f) { return !!f && !!this.hello && (this.hello.allowed || []).includes(f); }

  _show() {
    const s = this.state, f = s.flat, own = this._flatOk(f);
    const names = (this.hello && this.hello.names) || {};
    const who = f ? `${f}. lakás${names[f] ? ' (' + names[f] + ')' : ''}` : '';
    this.ring = s.state === 'ringing' && own;
    this.talk = s.state === 'talking' && own;
    const C = this.$('call');
    C.textContent = this.ring ? 'Csönget: ' + who : this.talk ? 'Beszélgetés: ' + who
      : s.state === 'ringing' || s.state === 'talking' ? `Hívás más lakásra (${f}.)` : s.state === 'line_down' ? 'Nincs vonal' : 'Nincs hívás';
    C.classList.toggle('ring', this.ring);
    this.may = this.talk;
    this.$('up').disabled = !this.ring;
    this.$('down').disabled = this.$('door').disabled = this.$('ptt').disabled = !this.may;
    if (this.ring && !this.node && !this.insecure) this.$('go').textContent = this.autoUp ? 'Felvétel és hang' : 'Hang bekapcsolása (belehallgatás)';
    if (!this.may && this.down) this._ptt(false);
    if ((this.ring || this.talk) && !this.listening && this.ws && this.ws.readyState === 1) {
      this.listening = true;
      this._cmd('listen', {on: true}, true);
    }
    if (!(this.ring || this.talk)) this.listening = false;
    if (this.ring && this.autoUp && this.node) { this.autoUp = false; this._cmd('up'); }
    if (this.ring && Date.now() - this.lastBeep > 2500) {
      this.lastBeep = Date.now();
      if (navigator.vibrate) navigator.vibrate([300, 150, 300]);
      this._beep();
    }
  }

  _event(j) {
    const t = {door: 'Ajtónyitás.', talk_ended: 'A hívás véget ért.', unanswered: 'Nem vették fel.', canceled: 'A hívó bontott.'}[j.event_type];
    if (t && this._flatOk(j.flat)) this.$('msg').textContent = t;
  }

  _beep() {
    const c = this.ctx; if (!c) return;
    [0, 0.35].forEach(t => {
      const o = new OscillatorNode(c, {frequency: 880}), g = new GainNode(c, {gain: 0.3});
      o.connect(g).connect(c.destination); o.start(c.currentTime + t); o.stop(c.currentTime + t + 0.2);
    });
  }

  _cmd(cmd, extra = {}, quiet = false) {
    if (!this.ws || this.ws.readyState !== 1) return;
    const id = ++this.cid;
    this.pending = this.pending || {};
    this.pending[id] = {cmd, quiet};
    if (!quiet) this.$('msg').textContent = '…';
    this.ws.send(JSON.stringify({t: 'cmd', id, cmd, flat: this.state.flat || 0, ...extra}));
  }

  _reply(j) {
    const p = (this.pending || {})[j.id] || {}; delete (this.pending || {})[j.id];
    if (!j.ok) {
      if (p.cmd === 'listen') this.listening = false;
      if (p.cmd === 'talk' && this.down) this._ptt(false, true);
      this.$('msg').textContent = j.msg || ERR_TEXT[j.error] || j.error;
      return;
    }
    const done = {up: 'Felvétel elküldve.', down: 'Letevés elküldve.', door: 'Ajtónyitás elküldve.'}[p.cmd];
    if (done) this.$('msg').textContent = done;
  }

  _ptt(on, local = false) {
    if (on === this.down || (on && (!this.may || !this.ws || this.ws.readyState !== 1))) return;
    this.down = on;
    const P = this.$('ptt');
    P.classList.toggle('on', on);
    P.textContent = on ? 'Beszélsz…' : 'Nyomd és beszélj';
    if (!local) this._cmd('talk', {on}, true);
    if (this.node) this.node.port.postMessage({ptt: on});
    if (navigator.vibrate) navigator.vibrate(30);
  }

  _sendTx(pcm) {
    if (!this.ws || this.ws.readyState !== 1) return;
    const f = new Uint8Array(4 + pcm.byteLength);
    f[0] = 2; f[1] = 0; f[2] = this.seq & 255; f[3] = (this.seq >> 8) & 255;
    this.seq = (this.seq + 1) & 0xffff;
    f.set(new Uint8Array(pcm.buffer, pcm.byteOffset, pcm.byteLength), 4);
    this.ws.send(f.buffer);
  }
}

customElements.define('codefon-panel', CodefonPanel);
