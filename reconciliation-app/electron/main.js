const {app,BrowserWindow,Menu}=require('electron');const path=require('path');
function create(){const w=new BrowserWindow({width:1200,height:820,title:'Smart Bank Reconciliation',icon:path.join(__dirname,'../app/icon-512.png'),webPreferences:{contextIsolation:true}});
Menu.setApplicationMenu(null);w.loadFile(path.join(__dirname,'../app/index.html'))}
app.whenReady().then(create);app.on('window-all-closed',()=>app.quit());
