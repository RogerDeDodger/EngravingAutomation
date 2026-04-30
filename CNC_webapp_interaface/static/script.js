// ------------------
// live plot
// ------------------

setInterval(function(){

    const img = document.getElementById("plot")

    if(img){
        img.src = "/plot.png?t=" + new Date().getTime()
    }

},200)


// ------------------
// machine state
// ------------------

setInterval(function(){

    fetch("/machine_state")
    .then(r=>r.json())
    .then(data=>{

        if(document.getElementById("mx")){

        document.getElementById("mx").innerText = data.mx.toFixed(2)
        document.getElementById("my").innerText = data.my.toFixed(2)
        document.getElementById("mz").innerText = data.mz.toFixed(2)

        }

    })

},500)


// ------------------
// keyboard jog
// ------------------

document.addEventListener("keydown", function(e){

    if(["w","a","s","d"].includes(e.key)){

        fetch("/jog",{
            method:"POST",
            headers:{
                "Content-Type":"application/json"
            },
            body:JSON.stringify({key:e.key})
        })

    }

})


// ------------------
// expandable menu
// ------------------

function toggleMenu(){

    const menu = document.getElementById("menu")

    if(menu.style.display=="none"){
        menu.style.display="block"
    }
    else{
        menu.style.display="none"
    }

}


// ------------------
// settings validation
// ------------------

function saveSettings(){

    const feed = document.getElementById("feedrate").value
    const tool = document.getElementById("tool").value

    fetch("/save_settings",{

        method:"POST",
        headers:{
            "Content-Type":"application/json"
        },

        body:JSON.stringify({
            feedrate:feed,
            tool:tool
        })

    })
    .then(r=>r.json())
    .then(data=>{

        const msg = document.getElementById("msg")

        if(data.status=="ok"){
            msg.innerText="saved"
        }
        else{
            msg.innerText=data.msg
        }

    })

}