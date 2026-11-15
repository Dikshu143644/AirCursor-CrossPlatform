(() => {
  const status = document.getElementById("status");
  const pad = document.getElementById("pad");
  const token = decodeURIComponent(location.hash.slice(1));
  let socket, active = false, lastSend = 0;
  const send = data => { if (active && socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify(data)); };
  function connect() {
    if (!token) { status.textContent = "Pair using the QR code"; return; }
    const scheme = location.protocol === "https:" ? "wss:" : "ws:";
    socket = new WebSocket(scheme + "//" + location.host + "/ws");
    socket.onopen = () => socket.send(JSON.stringify({type:"auth", token}));
    socket.onmessage = event => { const msg=JSON.parse(event.data); if(msg.type==="ready"){active=true;status.textContent="Connected";} };
    socket.onclose = () => { active=false; status.textContent="Disconnected"; };
    socket.onerror = () => status.textContent="Connection error";
  }
  pad.addEventListener("pointerdown", event => pad.setPointerCapture(event.pointerId));
  pad.addEventListener("pointermove", event => {
    if (!(event.buttons || event.pointerType === "touch")) return;
    const now=performance.now(); if(now-lastSend<16)return; lastSend=now;
    const rect=pad.getBoundingClientRect();
    send({type:"move",x:Math.max(0,Math.min(1,(event.clientX-rect.left)/rect.width)),y:Math.max(0,Math.min(1,(event.clientY-rect.top)/rect.height))});
  });
  document.getElementById("left").onclick=()=>send({type:"click",button:"left"});
  document.getElementById("right").onclick=()=>send({type:"click",button:"right"});
  document.getElementById("scrollUp").onclick=()=>send({type:"scroll",delta:3});
  document.getElementById("scrollDown").onclick=()=>send({type:"scroll",delta:-3});
  document.getElementById("recenter").onclick=()=>send({type:"button",button:"middle",action:"recenter"});
  document.getElementById("disconnect").onclick=()=>socket&&socket.close();
  connect();
})();
