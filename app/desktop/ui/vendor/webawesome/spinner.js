/**
 * @license
 * Copyright 2019 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */var I=globalThis,j=I.ShadowRoot&&(I.ShadyCSS===void 0||I.ShadyCSS.nativeShadow)&&"adoptedStyleSheets"in Document.prototype&&"replace"in CSSStyleSheet.prototype,X=Symbol(),he=new WeakMap,x=class{constructor(e,t,r){if(this._$cssResult$=!0,r!==X)throw Error("CSSResult is not constructable. Use `unsafeCSS` or `css` instead.");this.cssText=e,this.t=t}get styleSheet(){let e=this.o,t=this.t;if(j&&e===void 0){let r=t!==void 0&&t.length===1;r&&(e=he.get(t)),e===void 0&&((this.o=e=new CSSStyleSheet).replaceSync(this.cssText),r&&he.set(t,e))}return e}toString(){return this.cssText}},de=s=>new x(typeof s=="string"?s:s+"",void 0,X),P=(s,...e)=>{let t=s.length===1?s[0]:e.reduce((r,o,i)=>r+(n=>{if(n._$cssResult$===!0)return n.cssText;if(typeof n=="number")return n;throw Error("Value passed to 'css' function must be a 'css' function result: "+n+". Use 'unsafeCSS' to pass non-literal values, but take care to ensure page security.")})(o)+s[i+1],s[0]);return new x(t,s,X)},pe=(s,e)=>{if(j)s.adoptedStyleSheets=e.map(t=>t instanceof CSSStyleSheet?t:t.styleSheet);else for(let t of e){let r=document.createElement("style"),o=I.litNonce;o!==void 0&&r.setAttribute("nonce",o),r.textContent=t.cssText,s.appendChild(r)}},G=j?s=>s:s=>s instanceof CSSStyleSheet?(e=>{let t="";for(let r of e.cssRules)t+=r.cssText;return de(t)})(s):s;/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */var{is:je,defineProperty:qe,getOwnPropertyDescriptor:Be,getOwnPropertyNames:Fe,getOwnPropertySymbols:We,getPrototypeOf:Ve}=Object,q=globalThis,ue=q.trustedTypes,Ye=ue?ue.emptyScript:"",Ke=q.reactiveElementPolyfillSupport,R=(s,e)=>s,O={toAttribute(s,e){switch(e){case Boolean:s=s?Ye:null;break;case Object:case Array:s=s==null?s:JSON.stringify(s)}return s},fromAttribute(s,e){let t=s;switch(e){case Boolean:t=s!==null;break;case Number:t=s===null?null:Number(s);break;case Object:case Array:try{t=JSON.parse(s)}catch{t=null}}return t}},B=(s,e)=>!je(s,e),me={attribute:!0,type:String,converter:O,reflect:!1,useDefault:!1,hasChanged:B};Symbol.metadata??=Symbol("metadata"),q.litPropertyMetadata??=new WeakMap;var m=class extends HTMLElement{static addInitializer(e){this._$Ei(),(this.l??=[]).push(e)}static get observedAttributes(){return this.finalize(),this._$Eh&&[...this._$Eh.keys()]}static createProperty(e,t=me){if(t.state&&(t.attribute=!1),this._$Ei(),this.prototype.hasOwnProperty(e)&&((t=Object.create(t)).wrapped=!0),this.elementProperties.set(e,t),!t.noAccessor){let r=Symbol(),o=this.getPropertyDescriptor(e,r,t);o!==void 0&&qe(this.prototype,e,o)}}static getPropertyDescriptor(e,t,r){let{get:o,set:i}=Be(this.prototype,e)??{get(){return this[t]},set(n){this[t]=n}};return{get:o,set(n){let l=o?.call(this);i?.call(this,n),this.requestUpdate(e,l,r)},configurable:!0,enumerable:!0}}static getPropertyOptions(e){return this.elementProperties.get(e)??me}static _$Ei(){if(this.hasOwnProperty(R("elementProperties")))return;let e=Ve(this);e.finalize(),e.l!==void 0&&(this.l=[...e.l]),this.elementProperties=new Map(e.elementProperties)}static finalize(){if(this.hasOwnProperty(R("finalized")))return;if(this.finalized=!0,this._$Ei(),this.hasOwnProperty(R("properties"))){let t=this.properties,r=[...Fe(t),...We(t)];for(let o of r)this.createProperty(o,t[o])}let e=this[Symbol.metadata];if(e!==null){let t=litPropertyMetadata.get(e);if(t!==void 0)for(let[r,o]of t)this.elementProperties.set(r,o)}this._$Eh=new Map;for(let[t,r]of this.elementProperties){let o=this._$Eu(t,r);o!==void 0&&this._$Eh.set(o,t)}this.elementStyles=this.finalizeStyles(this.styles)}static finalizeStyles(e){let t=[];if(Array.isArray(e)){let r=new Set(e.flat(1/0).reverse());for(let o of r)t.unshift(G(o))}else e!==void 0&&t.push(G(e));return t}static _$Eu(e,t){let r=t.attribute;return r===!1?void 0:typeof r=="string"?r:typeof e=="string"?e.toLowerCase():void 0}constructor(){super(),this._$Ep=void 0,this.isUpdatePending=!1,this.hasUpdated=!1,this._$Em=null,this._$Ev()}_$Ev(){this._$ES=new Promise(e=>this.enableUpdating=e),this._$AL=new Map,this._$E_(),this.requestUpdate(),this.constructor.l?.forEach(e=>e(this))}addController(e){(this._$EO??=new Set).add(e),this.renderRoot!==void 0&&this.isConnected&&e.hostConnected?.()}removeController(e){this._$EO?.delete(e)}_$E_(){let e=new Map,t=this.constructor.elementProperties;for(let r of t.keys())this.hasOwnProperty(r)&&(e.set(r,this[r]),delete this[r]);e.size>0&&(this._$Ep=e)}createRenderRoot(){let e=this.shadowRoot??this.attachShadow(this.constructor.shadowRootOptions);return pe(e,this.constructor.elementStyles),e}connectedCallback(){this.renderRoot??=this.createRenderRoot(),this.enableUpdating(!0),this._$EO?.forEach(e=>e.hostConnected?.())}enableUpdating(e){}disconnectedCallback(){this._$EO?.forEach(e=>e.hostDisconnected?.())}attributeChangedCallback(e,t,r){this._$AK(e,r)}_$ET(e,t){let r=this.constructor.elementProperties.get(e),o=this.constructor._$Eu(e,r);if(o!==void 0&&r.reflect===!0){let i=(r.converter?.toAttribute!==void 0?r.converter:O).toAttribute(t,r.type);this._$Em=e,i==null?this.removeAttribute(o):this.setAttribute(o,i),this._$Em=null}}_$AK(e,t){let r=this.constructor,o=r._$Eh.get(e);if(o!==void 0&&this._$Em!==o){let i=r.getPropertyOptions(o),n=typeof i.converter=="function"?{fromAttribute:i.converter}:i.converter?.fromAttribute!==void 0?i.converter:O;this._$Em=o;let l=n.fromAttribute(t,i.type);this[o]=l??this._$Ej?.get(o)??l,this._$Em=null}}requestUpdate(e,t,r,o=!1,i){if(e!==void 0){let n=this.constructor;if(o===!1&&(i=this[e]),r??=n.getPropertyOptions(e),!((r.hasChanged??B)(i,t)||r.useDefault&&r.reflect&&i===this._$Ej?.get(e)&&!this.hasAttribute(n._$Eu(e,r))))return;this.C(e,t,r)}this.isUpdatePending===!1&&(this._$ES=this._$EP())}C(e,t,{useDefault:r,reflect:o,wrapped:i},n){r&&!(this._$Ej??=new Map).has(e)&&(this._$Ej.set(e,n??t??this[e]),i!==!0||n!==void 0)||(this._$AL.has(e)||(this.hasUpdated||r||(t=void 0),this._$AL.set(e,t)),o===!0&&this._$Em!==e&&(this._$Eq??=new Set).add(e))}async _$EP(){this.isUpdatePending=!0;try{await this._$ES}catch(t){Promise.reject(t)}let e=this.scheduleUpdate();return e!=null&&await e,!this.isUpdatePending}scheduleUpdate(){return this.performUpdate()}performUpdate(){if(!this.isUpdatePending)return;if(!this.hasUpdated){if(this.renderRoot??=this.createRenderRoot(),this._$Ep){for(let[o,i]of this._$Ep)this[o]=i;this._$Ep=void 0}let r=this.constructor.elementProperties;if(r.size>0)for(let[o,i]of r){let{wrapped:n}=i,l=this[o];n!==!0||this._$AL.has(o)||l===void 0||this.C(o,void 0,i,l)}}let e=!1,t=this._$AL;try{e=this.shouldUpdate(t),e?(this.willUpdate(t),this._$EO?.forEach(r=>r.hostUpdate?.()),this.update(t)):this._$EM()}catch(r){throw e=!1,this._$EM(),r}e&&this._$AE(t)}willUpdate(e){}_$AE(e){this._$EO?.forEach(t=>t.hostUpdated?.()),this.hasUpdated||(this.hasUpdated=!0,this.firstUpdated(e)),this.updated(e)}_$EM(){this._$AL=new Map,this.isUpdatePending=!1}get updateComplete(){return this.getUpdateComplete()}getUpdateComplete(){return this._$ES}shouldUpdate(e){return!0}update(e){this._$Eq&&=this._$Eq.forEach(t=>this._$ET(t,this[t])),this._$EM()}updated(e){}firstUpdated(e){}};m.elementStyles=[],m.shadowRootOptions={mode:"open"},m[R("elementProperties")]=new Map,m[R("finalized")]=new Map,Ke?.({ReactiveElement:m}),(q.reactiveElementVersions??=[]).push("2.1.2");/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */var re=globalThis,fe=s=>s,F=re.trustedTypes,ge=F?F.createPolicy("lit-html",{createHTML:s=>s}):void 0,Se="$lit$",$=`lit$${Math.random().toFixed(9).slice(2)}$`,we="?"+$,Xe=`<${we}>`,A=document,M=()=>A.createComment(""),N=s=>s===null||typeof s!="object"&&typeof s!="function",oe=Array.isArray,Ge=s=>oe(s)||typeof s?.[Symbol.iterator]=="function",Z=`[ 	
\f\r]`,T=/<(?:(!--|\/[^a-zA-Z])|(\/?[a-zA-Z][^>\s]*)|(\/?$))/g,$e=/-->/g,ye=/>/g,_=RegExp(`>|${Z}(?:([^\\s"'>=/]+)(${Z}*=${Z}*(?:[^ 	
\f\r"'\`<>=]|("|')|))|$)`,"g"),_e=/'/g,ve=/"/g,be=/^(?:script|style|textarea|title)$/i,ie=s=>(e,...t)=>({_$litType$:s,strings:e,values:t}),Ce=ie(1),pt=ie(2),ut=ie(3),S=Symbol.for("lit-noChange"),d=Symbol.for("lit-nothing"),Ae=new WeakMap,v=A.createTreeWalker(A,129);function Ee(s,e){if(!oe(s)||!s.hasOwnProperty("raw"))throw Error("invalid template strings array");return ge!==void 0?ge.createHTML(e):e}var Ze=(s,e)=>{let t=s.length-1,r=[],o,i=e===2?"<svg>":e===3?"<math>":"",n=T;for(let l=0;l<t;l++){let a=s[l],h,p,c=-1,u=0;for(;u<a.length&&(n.lastIndex=u,p=n.exec(a),p!==null);)u=n.lastIndex,n===T?p[1]==="!--"?n=$e:p[1]!==void 0?n=ye:p[2]!==void 0?(be.test(p[2])&&(o=RegExp("</"+p[2],"g")),n=_):p[3]!==void 0&&(n=_):n===_?p[0]===">"?(n=o??T,c=-1):p[1]===void 0?c=-2:(c=n.lastIndex-p[2].length,h=p[1],n=p[3]===void 0?_:p[3]==='"'?ve:_e):n===ve||n===_e?n=_:n===$e||n===ye?n=T:(n=_,o=void 0);let g=n===_&&s[l+1].startsWith("/>")?" ":"";i+=n===T?a+Xe:c>=0?(r.push(h),a.slice(0,c)+Se+a.slice(c)+$+g):a+$+(c===-2?l:g)}return[Ee(s,i+(s[t]||"<?>")+(e===2?"</svg>":e===3?"</math>":"")),r]},U=class s{constructor({strings:e,_$litType$:t},r){let o;this.parts=[];let i=0,n=0,l=e.length-1,a=this.parts,[h,p]=Ze(e,t);if(this.el=s.createElement(h,r),v.currentNode=this.el.content,t===2||t===3){let c=this.el.content.firstChild;c.replaceWith(...c.childNodes)}for(;(o=v.nextNode())!==null&&a.length<l;){if(o.nodeType===1){if(o.hasAttributes())for(let c of o.getAttributeNames())if(c.endsWith(Se)){let u=p[n++],g=o.getAttribute(c).split($),z=/([.?@])?(.*)/.exec(u);a.push({type:1,index:i,name:z[2],strings:g,ctor:z[1]==="."?Q:z[1]==="?"?ee:z[1]==="@"?te:b}),o.removeAttribute(c)}else c.startsWith($)&&(a.push({type:6,index:i}),o.removeAttribute(c));if(be.test(o.tagName)){let c=o.textContent.split($),u=c.length-1;if(u>0){o.textContent=F?F.emptyScript:"";for(let g=0;g<u;g++)o.append(c[g],M()),v.nextNode(),a.push({type:2,index:++i});o.append(c[u],M())}}}else if(o.nodeType===8)if(o.data===we)a.push({type:2,index:i});else{let c=-1;for(;(c=o.data.indexOf($,c+1))!==-1;)a.push({type:7,index:i}),c+=$.length-1}i++}}static createElement(e,t){let r=A.createElement("template");return r.innerHTML=e,r}};function w(s,e,t=s,r){if(e===S)return e;let o=r!==void 0?t._$Co?.[r]:t._$Cl,i=N(e)?void 0:e._$litDirective$;return o?.constructor!==i&&(o?._$AO?.(!1),i===void 0?o=void 0:(o=new i(s),o._$AT(s,t,r)),r!==void 0?(t._$Co??=[])[r]=o:t._$Cl=o),o!==void 0&&(e=w(s,o._$AS(s,e.values),o,r)),e}var J=class{constructor(e,t){this._$AV=[],this._$AN=void 0,this._$AD=e,this._$AM=t}get parentNode(){return this._$AM.parentNode}get _$AU(){return this._$AM._$AU}u(e){let{el:{content:t},parts:r}=this._$AD,o=(e?.creationScope??A).importNode(t,!0);v.currentNode=o;let i=v.nextNode(),n=0,l=0,a=r[0];for(;a!==void 0;){if(n===a.index){let h;a.type===2?h=new k(i,i.nextSibling,this,e):a.type===1?h=new a.ctor(i,a.name,a.strings,this,e):a.type===6&&(h=new se(i,this,e)),this._$AV.push(h),a=r[++l]}n!==a?.index&&(i=v.nextNode(),n++)}return v.currentNode=A,o}p(e){let t=0;for(let r of this._$AV)r!==void 0&&(r.strings!==void 0?(r._$AI(e,r,t),t+=r.strings.length-2):r._$AI(e[t])),t++}},k=class s{get _$AU(){return this._$AM?._$AU??this._$Cv}constructor(e,t,r,o){this.type=2,this._$AH=d,this._$AN=void 0,this._$AA=e,this._$AB=t,this._$AM=r,this.options=o,this._$Cv=o?.isConnected??!0}get parentNode(){let e=this._$AA.parentNode,t=this._$AM;return t!==void 0&&e?.nodeType===11&&(e=t.parentNode),e}get startNode(){return this._$AA}get endNode(){return this._$AB}_$AI(e,t=this){e=w(this,e,t),N(e)?e===d||e==null||e===""?(this._$AH!==d&&this._$AR(),this._$AH=d):e!==this._$AH&&e!==S&&this._(e):e._$litType$!==void 0?this.$(e):e.nodeType!==void 0?this.T(e):Ge(e)?this.k(e):this._(e)}O(e){return this._$AA.parentNode.insertBefore(e,this._$AB)}T(e){this._$AH!==e&&(this._$AR(),this._$AH=this.O(e))}_(e){this._$AH!==d&&N(this._$AH)?this._$AA.nextSibling.data=e:this.T(A.createTextNode(e)),this._$AH=e}$(e){let{values:t,_$litType$:r}=e,o=typeof r=="number"?this._$AC(e):(r.el===void 0&&(r.el=U.createElement(Ee(r.h,r.h[0]),this.options)),r);if(this._$AH?._$AD===o)this._$AH.p(t);else{let i=new J(o,this),n=i.u(this.options);i.p(t),this.T(n),this._$AH=i}}_$AC(e){let t=Ae.get(e.strings);return t===void 0&&Ae.set(e.strings,t=new U(e)),t}k(e){oe(this._$AH)||(this._$AH=[],this._$AR());let t=this._$AH,r,o=0;for(let i of e)o===t.length?t.push(r=new s(this.O(M()),this.O(M()),this,this.options)):r=t[o],r._$AI(i),o++;o<t.length&&(this._$AR(r&&r._$AB.nextSibling,o),t.length=o)}_$AR(e=this._$AA.nextSibling,t){for(this._$AP?.(!1,!0,t);e!==this._$AB;){let r=fe(e).nextSibling;fe(e).remove(),e=r}}setConnected(e){this._$AM===void 0&&(this._$Cv=e,this._$AP?.(e))}},b=class{get tagName(){return this.element.tagName}get _$AU(){return this._$AM._$AU}constructor(e,t,r,o,i){this.type=1,this._$AH=d,this._$AN=void 0,this.element=e,this.name=t,this._$AM=o,this.options=i,r.length>2||r[0]!==""||r[1]!==""?(this._$AH=Array(r.length-1).fill(new String),this.strings=r):this._$AH=d}_$AI(e,t=this,r,o){let i=this.strings,n=!1;if(i===void 0)e=w(this,e,t,0),n=!N(e)||e!==this._$AH&&e!==S,n&&(this._$AH=e);else{let l=e,a,h;for(e=i[0],a=0;a<i.length-1;a++)h=w(this,l[r+a],t,a),h===S&&(h=this._$AH[a]),n||=!N(h)||h!==this._$AH[a],h===d?e=d:e!==d&&(e+=(h??"")+i[a+1]),this._$AH[a]=h}n&&!o&&this.j(e)}j(e){e===d?this.element.removeAttribute(this.name):this.element.setAttribute(this.name,e??"")}},Q=class extends b{constructor(){super(...arguments),this.type=3}j(e){this.element[this.name]=e===d?void 0:e}},ee=class extends b{constructor(){super(...arguments),this.type=4}j(e){this.element.toggleAttribute(this.name,!!e&&e!==d)}},te=class extends b{constructor(e,t,r,o,i){super(e,t,r,o,i),this.type=5}_$AI(e,t=this){if((e=w(this,e,t,0)??d)===S)return;let r=this._$AH,o=e===d&&r!==d||e.capture!==r.capture||e.once!==r.once||e.passive!==r.passive,i=e!==d&&(r===d||o);o&&this.element.removeEventListener(this.name,this,r),i&&this.element.addEventListener(this.name,this,e),this._$AH=e}handleEvent(e){typeof this._$AH=="function"?this._$AH.call(this.options?.host??this.element,e):this._$AH.handleEvent(e)}},se=class{constructor(e,t,r){this.element=e,this.type=6,this._$AN=void 0,this._$AM=t,this.options=r}get _$AU(){return this._$AM._$AU}_$AI(e){w(this,e)}};var Je=re.litHtmlPolyfillSupport;Je?.(U,k),(re.litHtmlVersions??=[]).push("3.3.3");var xe=(s,e,t)=>{let r=t?.renderBefore??e,o=r._$litPart$;if(o===void 0){let i=t?.renderBefore??null;r._$litPart$=o=new k(e.insertBefore(M(),i),i,void 0,t??{})}return o._$AI(s),o};/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */var ne=globalThis,y=class extends m{constructor(){super(...arguments),this.renderOptions={host:this},this._$Do=void 0}createRenderRoot(){let e=super.createRenderRoot();return this.renderOptions.renderBefore??=e.firstChild,e}update(e){let t=this.render();this.hasUpdated||(this.renderOptions.isConnected=this.isConnected),super.update(e),this._$Do=xe(t,this.renderRoot,this.renderOptions)}connectedCallback(){super.connectedCallback(),this._$Do?.setConnected(!0)}disconnectedCallback(){super.disconnectedCallback(),this._$Do?.setConnected(!1)}render(){return S}};y._$litElement$=!0,y.finalized=!0,ne.litElementHydrateSupport?.({LitElement:y});var Qe=ne.litElementPolyfillSupport;Qe?.({LitElement:y});(ne.litElementVersions??=[]).push("4.2.2");/**
 * @license
 * Copyright 2022 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 *//*! Copyright 2026 Fonticons, Inc. - https://webawesome.com/license */var Pe=P`
  :host {
    --track-width: 2px;
    --track-color: var(--wa-color-neutral-fill-normal);
    --indicator-color: var(--wa-color-brand-fill-loud);
    --speed: 2s;
    --size: 1em;

    /*
      Resizing a spinner element using anything but font-size will break the animation because the animation uses em
      units. Therefore, if a spinner is used in a flex container without \`flex: none\` applied, the spinner can
      grow/shrink and break the animation. The use of \`flex: none\` on the host element prevents this by always having
      the spinner sized according to its actual dimensions.
    */
    flex: none;
    display: inline-flex;
    width: var(--size);
    height: var(--size);
  }

  svg {
    width: 100%;
    height: 100%;
    aspect-ratio: 1;
    animation: spin var(--speed) linear infinite;
  }

  .track,
  .indicator {
    --radius: calc(var(--size) / 2 - var(--track-width) / 2);
    --circumference: calc(var(--radius) * 2 * 3.141592654);

    cx: calc(var(--size) / 2);
    cy: calc(var(--size) / 2);
    r: var(--radius);
    fill: none;
    stroke-width: var(--track-width);
  }

  .track {
    stroke: var(--track-color);
  }

  .indicator {
    stroke: var(--indicator-color);
    stroke-linecap: round;
    stroke-dasharray: calc(0.597 * var(--circumference)), calc(0.796 * var(--circumference));
    stroke-dashoffset: calc(-0.04 * var(--circumference));
    animation: dash 1.5s ease-in-out infinite;
  }

  @keyframes spin {
    0% {
      transform: rotate(0deg);
    }
    100% {
      transform: rotate(360deg);
    }
  }

  @keyframes dash {
    0% {
      stroke-dasharray: calc(0.008 * var(--circumference)), calc(1.194 * var(--circumference));
      stroke-dashoffset: 0;
    }
    50% {
      stroke-dasharray: calc(0.716 * var(--circumference)), calc(1.194 * var(--circumference));
      stroke-dashoffset: calc(-0.278 * var(--circumference));
    }
    100% {
      stroke-dasharray: calc(0.716 * var(--circumference)), calc(1.194 * var(--circumference));
      stroke-dashoffset: calc(-0.987 * var(--circumference));
    }
  }
`;/*! Copyright 2026 Fonticons, Inc. - https://webawesome.com/license */var et=Object.defineProperty,tt=Object.getOwnPropertyDescriptor,Re=s=>{throw TypeError(s)},C=(s,e,t,r)=>{for(var o=r>1?void 0:r?tt(e,t):e,i=s.length-1,n;i>=0;i--)(n=s[i])&&(o=(r?n(e,t,o):n(o))||o);return r&&o&&et(e,t,o),o},Oe=(s,e,t)=>e.has(s)||Re("Cannot "+t),Te=(s,e,t)=>(Oe(s,e,"read from private field"),t?t.call(s):e.get(s)),Me=(s,e,t)=>e.has(s)?Re("Cannot add the same private member more than once"):e instanceof WeakSet?e.add(s):e.set(s,t),Ne=(s,e,t,r)=>(Oe(s,e,"write to private field"),r?r.call(s,t):e.set(s,t),t);/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */var Ue=s=>(e,t)=>{t!==void 0?t.addInitializer(()=>{customElements.define(s,e)}):customElements.define(s,e)};/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */var st={attribute:!0,type:String,converter:O,reflect:!1,hasChanged:B},rt=(s=st,e,t)=>{let{kind:r,metadata:o}=t,i=globalThis.litPropertyMetadata.get(o);if(i===void 0&&globalThis.litPropertyMetadata.set(o,i=new Map),r==="setter"&&((s=Object.create(s)).wrapped=!0),i.set(t.name,s),r==="accessor"){let{name:n}=t;return{set(l){let a=e.get.call(this);e.set.call(this,l),this.requestUpdate(n,a,s,!0,l)},init(l){return l!==void 0&&this.C(n,void 0,s,l),l}}}if(r==="setter"){let{name:n}=t;return function(l){let a=this[n];e.call(this,l),this.requestUpdate(n,a,s,!0,l)}}throw Error("Unsupported decorator location: "+r)};function D(s){return(e,t)=>typeof t=="object"?rt(s,e,t):((r,o,i)=>{let n=o.hasOwnProperty(i);return o.constructor.createProperty(i,r),n?Object.getOwnPropertyDescriptor(o,i):void 0})(s,e,t)}/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 *//**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 *//**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 *//**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 *//**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 *//**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 *//**
 * @license
 * Copyright 2021 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 *//**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 *//*! Copyright 2026 Fonticons, Inc. - https://webawesome.com/license */var it=P`
  :host {
    box-sizing: border-box;
  }

  :host *,
  :host *::before,
  :host *::after {
    box-sizing: inherit;
  }

  [hidden],
  :host([hidden]) {
    display: none !important;
  }
`,nt=/;\s+$/;function at(s){return s.replace(/[A-Z]/g,e=>`-${e.toLowerCase()}`)}function ke(s){let{property:e,value:t,element:r}=s;if(t){let o=r.getAttribute("style")||"";o&&(o.match(nt)||(o+=";"),o+=" ");let i=`${e}: ${t}`;return o.includes(i)?void 0:`${o}${i};`}return null}var V,H=class extends y{constructor(){super(),Me(this,V,!1),this.initialReflectedProperties=new Map,this.didSSR=!!this.shadowRoot,this.customStates={set:(e,t)=>{if(this.internals?.states)try{t?this.internals.states.add(e):this.internals.states.delete(e)}catch(r){if(String(r).includes("must start with '--'"))console.error("Your browser implements an outdated version of CustomStateSet. Consider using a polyfill");else throw r}},has:e=>{if(!this.internals?.states)return!1;try{return this.internals.states.has(e)}catch{return!1}}};try{this.internals=this.attachInternals()}catch{console.error("Element internals are not supported in your browser. Consider using a polyfill")}this.customStates.set("wa-defined",!0);let s=this.constructor;for(let[e,t]of s.elementProperties)t.default==="inherit"&&t.initial!==void 0&&typeof e=="string"&&this.customStates.set(`initial-${e}-${t.initial}`,!0)}static get styles(){let s=Array.isArray(this.css)?this.css:this.css?[this.css]:[];return[it,...s]}connectedCallback(){super.connectedCallback(),this.didSSR||this.shadowRoot?.prepend(document.createComment(` Web Awesome: https://webawesome.com/docs/components/${this.localName.replace("wa-","")} `)),this.didSSR&&this.updateComplete.then(()=>{this.shadowRoot?.prepend(document.createComment(` Web Awesome: https://webawesome.com/docs/components/${this.localName.replace("wa-","")} `))})}attributeChangedCallback(s,e,t){Te(this,V)||(this.constructor.elementProperties.forEach((r,o)=>{r.reflect&&this[o]!=null&&this.initialReflectedProperties.set(o,this[o])}),Ne(this,V,!0)),super.attributeChangedCallback(s,e,t)}willUpdate(s){super.willUpdate(s),this.initialReflectedProperties.forEach((e,t)=>{s.has(t)&&this[t]==null&&(this[t]=e)})}firstUpdated(s){super.firstUpdated(s),this.didSSR&&this.shadowRoot?.querySelectorAll("slot").forEach(e=>{e.dispatchEvent(new Event("slotchange",{bubbles:!0,composed:!1,cancelable:!1}))})}update(s){try{super.update(s)}catch(e){if(this.didSSR&&!this.hasUpdated){let t=new Event("lit-hydration-error",{bubbles:!0,composed:!0,cancelable:!1});t.error=e,this.dispatchEvent(t)}throw e}}setStyle(s,e){if(!this.style){let t=ke({property:at(s),value:e,element:this});t&&this.setAttribute("style",t);return}this.style[s]=e}setStyleProperty(s,e){if(!this.style){let t=ke({property:s,value:e,element:this});t&&this.setAttribute("style",t);return}this.style.setProperty(s,e)}relayNativeEvent(s,e){s.stopImmediatePropagation(),this.dispatchEvent(new s.constructor(s.type,{...s,...e}))}};V=new WeakMap;C([D()],H.prototype,"dir",2);C([D()],H.prototype,"lang",2);C([D({type:Boolean,reflect:!0,attribute:"did-ssr"})],H.prototype,"didSSR",2);var ae=new Set,E=new Map,f,le="ltr",ce="en",De=typeof MutationObserver<"u"&&typeof document<"u"&&typeof document.documentElement<"u";if(De){let s=new MutationObserver(He);le=document.documentElement.dir||"ltr",ce=document.documentElement.lang||navigator.language,s.observe(document.documentElement,{attributes:!0,attributeFilter:["dir","lang"]})}function L(...s){s.map(e=>{let t=e.$code.toLowerCase();E.has(t)?E.set(t,Object.assign(Object.assign({},E.get(t)),e)):E.set(t,e),f||(f=e)}),He()}function He(){De&&(le=document.documentElement.dir||"ltr",ce=document.documentElement.lang||navigator.language),[...ae.keys()].map(s=>{typeof s.requestUpdate=="function"&&s.requestUpdate()})}var Y=class{constructor(e){this.host=e,this.host.addController(this)}hostConnected(){ae.add(this.host)}hostDisconnected(){ae.delete(this.host)}dir(){return`${this.host.dir||le}`.toLowerCase()}lang(){let e=`${this.host.lang||ce}`.toLowerCase().replace(/_/g,"-");try{return new Intl.Locale(e),e}catch{return f?f.$code.toLowerCase():"en"}}getTranslationData(e){var t,r;let o;try{o=new Intl.Locale(e.replace(/_/g,"-"))}catch{return{locale:void 0,language:"",region:"",primary:void 0,secondary:void 0}}let i=o.language.toLowerCase(),n=(r=(t=o.region)===null||t===void 0?void 0:t.toLowerCase())!==null&&r!==void 0?r:"",l=E.get(`${i}-${n}`),a=E.get(i);return{locale:o,language:i,region:n,primary:l,secondary:a}}exists(e,t){var r;let{primary:o,secondary:i}=this.getTranslationData((r=t.lang)!==null&&r!==void 0?r:this.lang());return t=Object.assign({includeFallback:!1},t),!!(o&&o[e]||i&&i[e]||t.includeFallback&&f&&f[e])}term(e,...t){let{primary:r,secondary:o}=this.getTranslationData(this.lang()),i;if(r&&r[e])i=r[e];else if(o&&o[e])i=o[e];else if(f&&f[e])i=f[e];else return console.error(`No translation found for: ${String(e)}`),String(e);return typeof i=="function"?i(...t):i}date(e,t){return e=new Date(e),new Intl.DateTimeFormat(this.lang(),t).format(e)}number(e,t){return e=Number(e),isNaN(e)?"":new Intl.NumberFormat(this.lang(),t).format(e)}relativeTime(e,t,r){return new Intl.RelativeTimeFormat(this.lang(),r).format(e,t)}};/*! Copyright 2026 Fonticons, Inc. - https://webawesome.com/license */var Le={$code:"en",$name:"English",$dir:"ltr",allTagsRemoved:"All tags removed",am:"AM",autosizeColumn:"Autosize column",captions:"Captions",carousel:"Carousel",chooseDate:"Choose date",chooseDecade:"Choose decade",chooseMonth:"Choose month",chooseTime:"Choose time",chooseYear:"Choose year",clearEntry:"Clear entry",clearFilter:"Clear filter",clearSort:"Clear sort",close:"Close",closeCalendar:"Close calendar",closeTimeInput:"Close time picker",collapseRow:"Collapse row",columnMenu:"Column options",columnMovedToPosition:(s,e,t)=>`${s} moved to position ${e} of ${t}`,columns:"Columns",compactPageXOfY:(s,e)=>`${s} of ${e}`,completed:"Completed",copied:"Copied",copy:"Copy",createOption:s=>`Create "${s}"`,currentlyPlaying:"currently playing",currentValue:"Current value",date:"Date",datePickerKeyboardHelp:"Use arrow keys to change values; press Alt+Down Arrow to open the calendar.",day:"Day",dayPeriod:"AM/PM",decrement:"Decrement",deselectAllRows:"Deselect all rows",disabled:"Disabled",dropFileHere:"Drop file here or click to browse",dropFilesHere:"Drop files here or click to browse",empty:"Empty",endDate:"End date",enterFullscreen:"Enter fullscreen",error:"Error",exitFullscreen:"Exit fullscreen",expandRow:"Expand row",filterByColumn:s=>`Filter by ${s}`,filterFrom:"From",filterMax:"Max",filterMin:"Min",filterTo:"To",firstPage:"First page",goToSlide:(s,e)=>`Go to slide ${s} of ${e}`,hideColumn:"Hide column",hidePassword:"Hide password",hour:"Hour",incompleteDate:"Enter a valid date.",increment:"Increment",jumpBackwardX:s=>`Jump back ${s} pages`,jumpForwardX:s=>`Jump forward ${s} pages`,lastPage:"Last page",loading:"Loading",locked:"Locked",minute:"Minute",month:"Month",moreOptions:"More Options",mute:"Mute",nextDecade:"Next decade",nextMonth:"Next month",nextPage:"Next page",nextSlide:"Next slide",nextVideo:"Next Video",nextYear:"Next year",noData:"No data",noOptions:"No options",noResults:"No matching results",notCompleted:"Not completed",now:"Now",numCharacters:s=>s===1?"1 character":`${s} characters`,numCharactersRemaining:s=>s===1?"1 character remaining":`${s} characters remaining`,numOptionsAvailable:s=>s===0?"No options available":s===1?"1 option available":`${s} options available`,numOptionsSelected:s=>s===0?"No options selected":s===1?"1 option selected":`${s} options selected`,numRowsCopied:s=>s===1?"1 row copied":`${s} rows copied`,numRowsSelected:s=>s===1?"1 row selected":`${s} rows selected`,optionPosition:(s,e,t)=>`${s}, ${e} of ${t}`,optionsLoadError:"Options could not be loaded",pageXOfY:(s,e)=>`Page ${s} of ${e}`,pagination:"Pagination",pause:"Pause",pauseAnimation:"Pause animation",pictureInPicture:"Picture in picture",pinLeft:"Pin left",pinRight:"Pin right",play:"Play",playAnimation:"Play animation",playbackSpeed:"Playback speed",playlist:"Playlist",pm:"PM",previousDecade:"Previous decade",previousMonth:"Previous month",previousPage:"Previous page",previousSlide:"Previous slide",previousVideo:"Previous video",previousYear:"Previous year",progress:"Progress",rangeTooLong:s=>s===1?"Select a range no longer than 1 day":`Select a range no longer than ${s} days`,rangeTooShort:s=>s===1?"Select a range at least 1 day long":`Select a range at least ${s} days long`,readonly:"Read-only",remove:"Remove",resetColumns:"Reset columns",resize:"Resize",resizeColumn:"Resize column",rowsPerPage:"Rows per page",scrollableRegion:"Scrollable region",scrollToEnd:"Scroll to end",scrollToStart:"Scroll to start",search:"Search",second:"Second",seek:"Seek",seekProgress:(s,e)=>`${s} of ${e}`,selectAColorFromTheScreen:"Select a color from the screen",selectAllRows:"Select all rows",selected:"Selected",selectedDateLabel:s=>`Selected: ${s}`,selectedRangeLabel:s=>`Selected range: ${s}`,selectGroup:"Select group",selectionCleared:"Selection cleared",selectRow:"Select row",showingNofMRows:(s,e)=>`Showing ${s} of ${e} rows`,showingXtoYofZ:(s,e,t)=>`${s}\u2013${e} of ${t}`,showPassword:"Show password",slideNum:s=>`Slide ${s}`,sortAscending:"Sort ascending",sortColumn:"Sort column",sortDescending:"Sort descending",startDate:"Start date",steps:"Steps",stepXOfY:(s,e)=>`Step ${s} of ${e}`,tagAdded:s=>`${s} added`,tagAlreadyAdded:s=>`${s} is already added`,tagInputKeyboardHelp:"Press Backspace or Delete to remove this tag.",tagRemoved:s=>`${s} removed`,time:"Time",timeInputKeyboardHelp:"Use arrow keys to change values; press Alt+Down Arrow to open the time picker.",today:"Today",toggleColorFormat:"Toggle color format",tooFewTags:s=>s===1?"Add at least 1 tag":`Add at least ${s} tags`,tooManyTags:s=>s===1?"Add no more than 1 tag":`Add no more than ${s} tags`,unmute:"Unmute",unpin:"Unpin",unpinColumn:"Unpin column",videoPlayer:"Video player",volume:"Volume",year:"Year",zoomIn:"Zoom in",zoomOut:"Zoom out"};L(Le);var ze=Le;/*! Copyright 2026 Fonticons, Inc. - https://webawesome.com/license */var Ie=class extends Y{lang(){return this.host.didSSR&&!this.host.hasUpdated?this.host.lang||"en":super.lang()}};L(ze);/*! Copyright 2026 Fonticons, Inc. - https://webawesome.com/license */var K=class extends H{constructor(){super(...arguments),this.localize=new Ie(this)}render(){return Ce`
      <svg
        part="base spinner"
        role="progressbar"
        aria-label=${this.localize.term("loading")}
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
      >
        <circle class="track" />
        <circle class="indicator" />
      </svg>
    `}};K.css=Pe;K=C([Ue("wa-spinner")],K);/*! Copyright 2026 Fonticons, Inc. - https://webawesome.com/license */export{K as default};
