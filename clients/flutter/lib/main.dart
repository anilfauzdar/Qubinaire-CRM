
import 'dart:convert';
import 'dart:io';
import 'dart:async';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:sqflite/sqflite.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';
import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:uuid/uuid.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  if (Platform.isWindows) {
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfi;
  }
  runApp(const QubinaireApp());
}

class LocalStore {
  static const modules=['users','activities','followups','daily_reports','courses','admissions','payments','targets','attendance','leave_requests','refund_requests','incentive_payouts','incentive_settings'];
  static const readOnlyModules=['users'];
  static Database? _db; static int? _dbUserId;
  static Future<Database> get db async {
    final prefs=await SharedPreferences.getInstance();
    final userId=prefs.getInt('crm_user_id')??0;
    if (_db != null && _dbUserId==userId) return _db!;
    if (_db != null) { await _db!.close(); _db=null; }
    final dir = await getApplicationDocumentsDirectory();
    _db = await openDatabase(p.join(dir.path, 'qubinaire_local_$userId.db'), version: 1,
      onCreate: (d, v) async {
        await d.execute('''CREATE TABLE leads(id TEXT PRIMARY KEY, name TEXT NOT NULL,
          lead_type TEXT NOT NULL, phone TEXT, city TEXT, status TEXT, owner_id INTEGER,
          updated_at TEXT, sync_state TEXT NOT NULL DEFAULT 'pending')''');
        await d.execute('''CREATE TABLE outbox(id TEXT PRIMARY KEY, entity TEXT NOT NULL,
          operation TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL)''');
        await d.execute('''CREATE TABLE module_records(module TEXT NOT NULL, record_id TEXT NOT NULL, payload TEXT NOT NULL, updated_at TEXT NOT NULL, sync_state TEXT NOT NULL DEFAULT 'synced', PRIMARY KEY(module,record_id))''');
        await d.execute('''CREATE TABLE id_mappings(local_id TEXT PRIMARY KEY, server_id TEXT NOT NULL, entity TEXT NOT NULL)''');
      });
    _dbUserId=userId;
    final leadCols=(await _db!.rawQuery('PRAGMA table_info(leads)')).map((r)=>r['name'].toString()).toSet();
    if(!leadCols.contains('payload')) await _db!.execute('ALTER TABLE leads ADD COLUMN payload TEXT');
    if(!leadCols.contains('version')) await _db!.execute('ALTER TABLE leads ADD COLUMN version INTEGER NOT NULL DEFAULT 1');
    await _db!.execute('''CREATE TABLE IF NOT EXISTS module_records(module TEXT NOT NULL, record_id TEXT NOT NULL, payload TEXT NOT NULL, updated_at TEXT NOT NULL, sync_state TEXT NOT NULL DEFAULT 'synced', PRIMARY KEY(module,record_id))''');
    await _db!.execute('''CREATE TABLE IF NOT EXISTS id_mappings(local_id TEXT PRIMARY KEY, server_id TEXT NOT NULL, entity TEXT NOT NULL)''');
    return _db!;
  }
  static Future<void> saveLead(Map<String,dynamic> lead) async {
    final d=await db;
    final id=lead['id']?.toString() ?? const Uuid().v4();
    final oldRows=await d.query('leads',where:'id=?',whereArgs:[id],limit:1);
    final old=oldRows.isEmpty?null:oldRows.first;
    final baseVersion=lead['base_version']??lead['version']??old?['version']??0;
    final data={...lead,'id':id,'base_version':baseVersion,'owner_id':lead['owner_id']??Api.userId,'updated_at':DateTime.now().toUtc().toIso8601String(),'sync_state':'pending'};
    await d.insert('leads',{'id':id,'name':data['name']??'','lead_type':data['lead_type']??'student','phone':data['phone'],'city':data['city'],'status':data['status']??'new','owner_id':data['owner_id'],'updated_at':data['updated_at'],'sync_state':'pending','payload':jsonEncode(data),'version':data['version']??baseVersion},conflictAlgorithm:ConflictAlgorithm.replace);
    await d.insert('outbox',{'id':'lead:$id','entity':'lead','operation':'upsert','payload':jsonEncode(data),'created_at':DateTime.now().toUtc().toIso8601String()},conflictAlgorithm:ConflictAlgorithm.replace);
  }
  static Future<void> saveModuleRecord(String module,Map<String,dynamic> payload,{String? recordId,Map<String,dynamic>? baseSnapshot}) async {
    final d=await db; final id=recordId??payload['id']?.toString()??'local:${const Uuid().v4()}';
    final data={...payload,'id':id,'_local_record_id':id};
    if(baseSnapshot!=null) data['_base_snapshot']=baseSnapshot;
    await d.insert('module_records',{'module':module,'record_id':id,'payload':jsonEncode(data),'updated_at':DateTime.now().toUtc().toIso8601String(),'sync_state':'pending'},conflictAlgorithm:ConflictAlgorithm.replace);
    await d.insert('outbox',{'id':'$module:$id','entity':module,'operation':'upsert','payload':jsonEncode(data),'created_at':DateTime.now().toUtc().toIso8601String()},conflictAlgorithm:ConflictAlgorithm.replace);
  }
  static Future<List<Map<String,dynamic>>> moduleRecords(String module) async {
    final rows=await (await db).query('module_records',where:'module=?',whereArgs:[module],orderBy:'updated_at DESC');
    return rows.map((r)=>{...Map<String,dynamic>.from(jsonDecode(r['payload'] as String)),'_sync_state':r['sync_state']}).toList();
  }
  static Future<List<Map<String,Object?>>> leads() async =>
      (await db).query('leads',orderBy:'updated_at DESC');
  static Future<int> pendingCount() async =>
      Sqflite.firstIntValue(await (await db).rawQuery('SELECT COUNT(*) FROM outbox')) ?? 0;
}

class Api {
  static String base='http://127.0.0.1:8080';
  static String? token, deviceId, deviceToken;
  static int? userId;
  static final secure = FlutterSecureStorage();
  static Future<void> load() async {
    final prefs=await SharedPreferences.getInstance();
    base=prefs.getString('api_base') ?? base;
    userId=prefs.getInt('crm_user_id');
    token=await secure.read(key:'user_token');
    deviceId=await secure.read(key:'device_id');
    deviceToken=await secure.read(key:'device_token');
  }
  static Future<void> logout() async {
    final prefs=await SharedPreferences.getInstance(); await prefs.remove('crm_user_id');
    await secure.delete(key:'user_token'); await secure.delete(key:'device_id'); await secure.delete(key:'device_token');
    token=null; deviceId=null; deviceToken=null; userId=null;
  }
  static Future<void> save(String url,String t) async {
    final prefs=await SharedPreferences.getInstance();
    await prefs.setString('api_base',url);
    await secure.write(key:'user_token',value:t);
    base=url; token=t;
  }
  static Future<String> login(String url,String username,String password) async {
    final r=await http.post(Uri.parse('$url/v1/auth/login'),
      headers:{'Content-Type':'application/json'},
      body:jsonEncode({'username':username,'password':password}));
    if(r.statusCode!=200) throw Exception('Login failed (${r.statusCode}): ${r.body}');
    final loginData=jsonDecode(r.body);
    final t=loginData['access_token'] as String;
    final prefs=await SharedPreferences.getInstance();
    final previousUserId=prefs.getInt('crm_user_id');
    userId=loginData['user']['id'] as int;
    await prefs.setInt('crm_user_id',userId!);
    await save(url,t);
    var deviceValid=false;
    if(previousUserId==userId && deviceToken!=null){
      try { await syncBootstrap(null); deviceValid=true; } catch (_) {}
    }
    if(!deviceValid) {
      await registerDevice(Platform.isAndroid?'Android device':'Windows device',Platform.isAndroid?'android':'windows');
    }
    return t;
  }
  static Future<void> registerDevice(String name,String platform) async {
    final r=await http.post(Uri.parse('$base/v1/devices/register'),
      headers:{'Content-Type':'application/json','Authorization':'Bearer $token'},
      body:jsonEncode({'device_name':name,'platform':platform}));
    if(r.statusCode!=200) throw Exception('Device registration failed (${r.statusCode}): ${r.body}');
    final data=jsonDecode(r.body);
    deviceId=data['device_id']; deviceToken=data['device_token'];
    await secure.write(key:'device_id',value:deviceId);
    await secure.write(key:'device_token',value:deviceToken);
  }
  static Future<Map<String,dynamic>> syncBootstrap(String? afterId) async {
    final q=afterId==null?'':'&after_id=${Uri.encodeQueryComponent(afterId)}';
    final r=await http.get(Uri.parse('$base/v1/sync/bootstrap?limit=500$q'),
      headers:{'Authorization':'Bearer $deviceToken'});
    if(r.statusCode!=200) throw Exception('Sync bootstrap failed (${r.statusCode}): ${r.body}');
    return jsonDecode(r.body);
  }
  static Future<Map<String,dynamic>> syncSnapshot(String module,int offset) async {
    final r=await http.get(Uri.parse('$base/v1/sync/snapshot/$module?limit=500&offset=$offset'),headers:{'Authorization':'Bearer $deviceToken'});
    if(r.statusCode!=200) throw Exception('Snapshot $module failed (${r.statusCode}): ${r.body}');
    return jsonDecode(r.body);
  }
  static Future<Map<String,dynamic>> syncPush(List<Map<String,dynamic>> changes) async {
    final r=await http.post(Uri.parse('$base/v1/sync/push'),
      headers:{'Content-Type':'application/json','Authorization':'Bearer $deviceToken'},
      body:jsonEncode({'device_id':deviceId,'changes':changes}));
    if(r.statusCode!=200) throw Exception('Sync push failed (${r.statusCode}): ${r.body}');
    return jsonDecode(r.body);
  }
  static Future<Map<String,dynamic>> syncPull(int sinceSeq) async {
    final q='?since_seq=$sinceSeq';
    final r=await http.get(Uri.parse('$base/v1/sync/pull$q'),
      headers:{'Authorization':'Bearer $deviceToken'});
    if(r.statusCode!=200) throw Exception('Sync pull failed (${r.statusCode}): ${r.body}');
    return jsonDecode(r.body);
  }
}
class QubinaireApp extends StatelessWidget {
  const QubinaireApp({super.key});
  @override Widget build(BuildContext context)=>MaterialApp(
    title:'Qubinaire CRM', theme:ThemeData(colorSchemeSeed:const Color(0xff2457c5),useMaterial3:true),
    home:const LoginPage());
}

class LoginPage extends StatefulWidget { const LoginPage({super.key}); @override State<LoginPage> createState()=>_LoginPageState(); }
class _LoginPageState extends State<LoginPage> {
  final url=TextEditingController(text:'http://127.0.0.1:8080');
  final user=TextEditingController(), pass=TextEditingController();
  bool busy=false; String error='';
  @override void initState(){super.initState(); Api.load().then((_){if(!mounted)return; if(Api.token!=null && Api.userId!=null && Api.deviceToken!=null){WidgetsBinding.instance.addPostFrameCallback((_) {if(mounted)Navigator.pushReplacement(context,MaterialPageRoute(builder:(_)=>const HomePage()));});} else {setState(()=>url.text=Api.base);}});}
  Future<void> go() async {
    setState(()=>busy=true); error='';
    try { await Api.login(url.text.trim(),user.text.trim(),pass.text); if(mounted) Navigator.pushReplacement(context,MaterialPageRoute(builder:(_)=>const HomePage())); }
    catch(e){setState(()=>error=e.toString());} finally {if(mounted)setState(()=>busy=false);}
  }
  @override Widget build(BuildContext c)=>Scaffold(body:Center(child:ConstrainedBox(constraints:const BoxConstraints(maxWidth:440),child:Card(
    margin:const EdgeInsets.all(24),child:Padding(padding:const EdgeInsets.all(24),child:Column(mainAxisSize:MainAxisSize.min,children:[
      const Text('QUBINAIRE CRM',style:TextStyle(fontSize:24,fontWeight:FontWeight.bold)),
      TextField(controller:url,decoration:const InputDecoration(labelText:'Central API URL')),
      TextField(controller:user,decoration:const InputDecoration(labelText:'Username')),
      TextField(controller:pass,obscureText:true,decoration:const InputDecoration(labelText:'Password')),
      if(error.isNotEmpty) Text(error,style:const TextStyle(color:Colors.red)),
      const SizedBox(height:12),FilledButton(onPressed:busy?null:go,child:Text(busy?'Signing in...':'Sign in'))
    ]))))));
}

class HomePage extends StatefulWidget { const HomePage({super.key}); @override State<HomePage> createState()=>_HomePageState(); }
class _HomePageState extends State<HomePage> with WidgetsBindingObserver {
  List<Map<String,Object?>> rows=[]; int pending=0, cachedAdmissions=0, pendingFollowups=0; double cachedCollections=0; String status='Offline-first · waiting for sync'; bool syncing=false;
  Timer? timer; StreamSubscription<List<ConnectivityResult>>? connectivitySub;
  @override void initState(){super.initState();WidgetsBinding.instance.addObserver(this);refresh();timer=Timer.periodic(const Duration(seconds:30),(_)=>syncNow());connectivitySub=Connectivity().onConnectivityChanged.listen((results){if(results.any((r)=>r!=ConnectivityResult.none))syncNow();});syncNow();}
  @override void dispose(){timer?.cancel();connectivitySub?.cancel();WidgetsBinding.instance.removeObserver(this);super.dispose();}
  @override void didChangeAppLifecycleState(AppLifecycleState state){if(state==AppLifecycleState.resumed)syncNow();}
  Future<void> refresh() async {rows=await LocalStore.leads();pending=await LocalStore.pendingCount();final admissions=await LocalStore.moduleRecords('admissions');final followups=await LocalStore.moduleRecords('followups');final payments=await LocalStore.moduleRecords('payments');cachedAdmissions=admissions.length;pendingFollowups=followups.where((r)=>r['status']=='pending').length;cachedCollections=payments.where((r)=>r['status']=='received').fold<double>(0,(sum,r)=>sum+(double.tryParse(r['amount']?.toString()??'0')??0));if(mounted)setState((){});}
  Future<void> syncNow() async {
    if(syncing || Api.deviceToken==null || Api.deviceId==null) return;
    syncing=true;
    try {
      final d=await LocalStore.db;
      final prefs=await SharedPreferences.getInstance();
      final bootKey='sync_bootstrapped_${Api.userId}';
      final cursorKey='sync_cursor_seq_${Api.userId}';
      if(!(prefs.getBool(bootKey)??false)){
        String? afterId; var firstSeq=0;
        do {
          final page=await Api.syncBootstrap(afterId);
          if(afterId==null) firstSeq=page['max_seq'] as int;
          for(final item in (page['items'] as List)){
            final lead=Map<String,dynamic>.from(item as Map);
            await d.insert('leads',{'id':lead['id'].toString(),'name':lead['name']??'',
              'lead_type':lead['lead_type']??'student','phone':lead['phone'],'city':lead['city'],
              'status':lead['status']??'new','owner_id':lead['owner_id'],
              'updated_at':lead['updated_at']?.toString(),'sync_state':'synced','payload':jsonEncode(lead),'version':lead['version']??1},
              conflictAlgorithm:ConflictAlgorithm.replace);
          }
          afterId=page['next_after_id'] as String?;
        } while(afterId!=null);
        await prefs.setInt(cursorKey,firstSeq);
        await prefs.setBool(bootKey,true);
      }
      // Bootstrap every writable CRM module into the per-user local cache.
      for(final module in LocalStore.modules){
        final moduleBoot='sync_boot_${module}_${Api.userId}';
        if((prefs.getBool(moduleBoot)??false) && module!='users') continue;
        var offset=0;
        do {
          final page=await Api.syncSnapshot(module,offset);
          final items=(page['items'] as List).cast<Map>();
          for(final item in items){
            final row=Map<String,dynamic>.from(item); final id=row['id'].toString();
            await d.insert('module_records',{'module':module,'record_id':id,'payload':jsonEncode(row),'updated_at':DateTime.now().toUtc().toIso8601String(),'sync_state':'synced'},conflictAlgorithm:module=='users'?ConflictAlgorithm.replace:ConflictAlgorithm.ignore);
          }
          final next=page['next_offset']; if(next==null) break; offset=next as int;
        } while(true);
        await prefs.setBool(moduleBoot,true);
      }
      final queued=await d.query('outbox',orderBy:'created_at ASC',limit:100);
      final mappingRows=await d.query('id_mappings');
      final idMap={for(final m in mappingRows) m['local_id'].toString():m['server_id'].toString()};
      if(queued.isNotEmpty){
        final changes=queued.map((r){
          final payload=jsonDecode(r['payload'] as String) as Map<String,dynamic>;
          payload['base_version']=payload['base_version']??0;
          for(final key in payload.keys.toList()){final value=payload[key];if(key.endsWith('_id') && value is String && idMap.containsKey(value)) payload[key]=idMap[value];}
          return {'change_id':r['id'],'entity':r['entity'],'record_id':payload['_local_record_id']??payload['id'],'operation':r['operation'],
            'payload':payload,'client_updated_at':r['created_at']};
        }).toList();
        final result=await Api.syncPush(changes);
        final acceptedRows=[...(result['accepted'] as List).cast<Map>(),...(result['duplicate_records'] as List? ?? const [])];
        final accepted=acceptedRows.map((x)=>x['change_id'].toString()).toSet();
        final duplicates=(result['duplicates'] as List).map((x)=>x.toString()).toSet();
        final rejected=(result['rejected'] as List).map((x)=>x['change_id'].toString()).toSet();
        for(final id in {...accepted,...duplicates}){
          await d.delete('outbox',where:'id=?',whereArgs:[id]);
          final queuedRow=queued.firstWhere((r)=>r['id']==id);
          var payload=jsonDecode(queuedRow['payload'] as String) as Map<String,dynamic>;
          if(queuedRow['entity']=='lead'){ Map? acceptedLead;for(final candidate in acceptedRows){if(candidate['change_id'].toString()==id){acceptedLead=candidate;break;}}final serverLead=acceptedLead?['server_record'];if(serverLead is Map){final clean=Map<String,dynamic>.from(serverLead);clean.remove('actor_id');clean.remove('server_id');clean.remove('server_version');await d.update('leads',{'name':clean['name']??'','lead_type':clean['lead_type']??'student','phone':clean['phone'],'city':clean['city'],'status':clean['status']??'new','owner_id':clean['owner_id'],'updated_at':clean['updated_at']?.toString(),'version':serverLead['server_version']??serverLead['version']??1,'payload':jsonEncode(clean),'sync_state':'synced'},where:'id=?',whereArgs:[payload['id']]);}else{await d.update('leads',{'sync_state':'synced'},where:'id=?',whereArgs:[payload['id']]);} }
          else {
            Map? acceptedRow; for(final candidate in acceptedRows){if(candidate['change_id'].toString()==id){acceptedRow=candidate;break;}}
            final localId=(acceptedRow?['local_record_id']??payload['_local_record_id']??payload['id']).toString();
            final serverId=(acceptedRow?['record_id']??localId).toString();
            final serverRecord=acceptedRow?['server_record'];
            if(serverRecord is Map){payload=Map<String,dynamic>.from(serverRecord);}
            payload['id']=serverId; payload['_local_record_id']=serverId; payload.remove('_base_snapshot'); payload.remove('server_id'); payload.remove('actor_id');
            if(localId!=serverId){
              await d.insert('id_mappings',{'local_id':localId,'server_id':serverId,'entity':queuedRow['entity']},conflictAlgorithm:ConflictAlgorithm.replace);
              await d.delete('module_records',where:'module=? AND record_id=?',whereArgs:[queuedRow['entity'],localId]);
            }
            await d.insert('module_records',{'module':queuedRow['entity'],'record_id':serverId,'payload':jsonEncode(payload),'updated_at':DateTime.now().toUtc().toIso8601String(),'sync_state':'synced'},conflictAlgorithm:ConflictAlgorithm.replace);
          }
        }
        for(final id in rejected){
          final queuedRow=queued.firstWhere((r)=>r['id']==id);
          var payload=jsonDecode(queuedRow['payload'] as String) as Map<String,dynamic>;
          await d.delete('outbox',where:'id=?',whereArgs:[id]);
          if(queuedRow['entity']=='lead') await d.update('leads',{'sync_state':'conflict'},where:'id=?',whereArgs:[payload['id']]); else await d.update('module_records',{'sync_state':'conflict'},where:'module=? AND record_id=?',whereArgs:[queuedRow['entity'],payload['_local_record_id']??payload['id']]);
        }
      }
      final since=prefs.getInt(cursorKey)??0;
      final pulled=await Api.syncPull(since);
      for(final change in (pulled['changes'] as List)){
        if(change['operation']!='upsert') continue;
        final payload=Map<String,dynamic>.from(change['payload'] as Map);
        final id=change['record_id'].toString();
        if(change['entity']=='lead') {
          await d.insert('leads',{'id':id,'name':payload['name']??'','lead_type':payload['lead_type']??'student','phone':payload['phone'],'city':payload['city'],'status':payload['status']??'new','owner_id':payload['owner_id'],'updated_at':change['received_at'].toString(),'sync_state':'synced','payload':jsonEncode(payload),'version':payload['version']??1},conflictAlgorithm:ConflictAlgorithm.replace);
        } else if(LocalStore.modules.contains(change['entity'])) {
          payload['id']=id; payload.remove('server_id'); payload.remove('actor_id');
          await d.insert('module_records',{'module':change['entity'],'record_id':id,'payload':jsonEncode(payload),'updated_at':change['received_at'].toString(),'sync_state':'synced'},conflictAlgorithm:ConflictAlgorithm.replace);
        }
      }
      if(pulled['next_since_seq']!=null) await prefs.setInt(cursorKey,pulled['next_since_seq'] as int);
      status='Synced · ${DateTime.now().toLocal().toString().substring(0,16)}';
    } catch(e){status='Sync pending: ${e.toString()}';}
    finally{syncing=false;if(mounted)await refresh();}
  }
  @override Widget build(BuildContext c)=>Scaffold(appBar:AppBar(title:const Text('Qubinaire CRM'),actions:[IconButton(onPressed:syncNow,icon:const Icon(Icons.sync)),IconButton(onPressed:()async{await Api.logout();if(c.mounted)Navigator.pushReplacement(c,MaterialPageRoute(builder:(_)=>const LoginPage()));},icon:const Icon(Icons.logout))]),
    floatingActionButton:FloatingActionButton(onPressed:()async{await Navigator.push(context,MaterialPageRoute(builder:(_)=>const NewLeadPage()));await refresh();syncNow();},child:const Icon(Icons.add)),
    body:RefreshIndicator(onRefresh:syncNow,child:ListView(padding:const EdgeInsets.all(16),children:[
      Card(child:ListTile(title:Text('${rows.length} locally stored leads'),subtitle:Text('$pending pending changes · $status'),trailing:const Icon(Icons.cloud_sync))),
      Card(child:ListTile(title:const Text('Offline dashboard snapshot'),subtitle:Text('$cachedAdmissions admissions · $pendingFollowups pending follow-ups · ₹${cachedCollections.toStringAsFixed(0)} received payments'))),
      const Padding(padding:EdgeInsets.symmetric(vertical:12),child:Text('CRM MODULES · Offline cache',style:TextStyle(fontWeight:FontWeight.bold))),
      Wrap(spacing:8,runSpacing:8,children:[for(final m in LocalStore.modules) ActionChip(label:Text(m.replaceAll('_',' ').toUpperCase()),onPressed:()=>Navigator.push(context,MaterialPageRoute(builder:(_)=>ModulePage(module:m))))]),
      for(final r in rows) Card(child:ListTile(onTap:()=>Navigator.push(context,MaterialPageRoute(builder:(_)=>LeadDraftPage(initial:r))).then((_)=>refresh()),title:Text('${r['name']??''}'),subtitle:Text('${r['lead_type']} · ${r['phone']??''} · ${r['city']??''}'),trailing:Text('${r['sync_state']}')))
    ])));
}
class NewLeadPage extends StatefulWidget { const NewLeadPage({super.key}); @override State<NewLeadPage> createState()=>_NewLeadPageState(); }
class _NewLeadPageState extends State<NewLeadPage> {
  final name=TextEditingController(), phone=TextEditingController(), city=TextEditingController();
  String type='student';
  @override Widget build(BuildContext c)=>Scaffold(appBar:AppBar(title:const Text('New lead')),body:Padding(padding:const EdgeInsets.all(20),child:ListView(children:[
    DropdownButtonFormField(value:type,items:const [DropdownMenuItem(value:'student',child:Text('Student')),DropdownMenuItem(value:'college',child:Text('College'))],onChanged:(v)=>setState(()=>type=v??'student')),
    TextField(controller:name,decoration:const InputDecoration(labelText:'Name')),
    TextField(controller:phone,decoration:const InputDecoration(labelText:'Phone')),
    TextField(controller:city,decoration:const InputDecoration(labelText:'City')),
    const SizedBox(height:20),FilledButton(onPressed:()async{if(name.text.trim().isEmpty)return;await LocalStore.saveLead({'name':name.text.trim(),'lead_type':type,'phone':phone.text.trim(),'city':city.text.trim(),'status':'new'});if(c.mounted)Navigator.pop(c);},child:const Text('Save locally'))
  ])));
}


class ModulePage extends StatefulWidget { final String module; const ModulePage({super.key,required this.module}); @override State<ModulePage> createState()=>_ModulePageState(); }
class _ModulePageState extends State<ModulePage> {
  List<Map<String,dynamic>> items=[];
  @override void initState(){super.initState();load();}
  Future<void> load() async { items=await LocalStore.moduleRecords(widget.module); if(mounted)setState((){}); }
  @override Widget build(BuildContext c)=>Scaffold(appBar:AppBar(title:Text(widget.module.replaceAll('_',' ').toUpperCase())),floatingActionButton:LocalStore.readOnlyModules.contains(widget.module)?null:FloatingActionButton(onPressed:()=>Navigator.push(c,MaterialPageRoute(builder:(_)=>ModuleDraftPage(module:widget.module))).then((_)=>load()),child:const Icon(Icons.add)),body:RefreshIndicator(onRefresh:load,child:ListView(padding:const EdgeInsets.all(12),children:[Text('${items.length} cached records · works offline',style:Theme.of(c).textTheme.bodySmall),for(final item in items) Card(child:ListTile(onTap:LocalStore.readOnlyModules.contains(widget.module)?null:()=>Navigator.push(c,MaterialPageRoute(builder:(_)=>ModuleDraftPage(module:widget.module,initial:item))).then((_)=>load()),title:Text((item['name']??item['admission_no']??item['id']??'Record').toString()),subtitle:Text(item.entries.where((e)=>e.key!='id').take(3).map((e)=>'${e.key}: ${e.value??''}').join(' · ')),trailing:Text((item['_sync_state']??'synced').toString())))])));
}
class ModuleDraftPage extends StatefulWidget { final String module; final Map<String,dynamic>? initial; const ModuleDraftPage({super.key,required this.module,this.initial}); @override State<ModuleDraftPage> createState()=>_ModuleDraftPageState(); }
class _ModuleDraftPageState extends State<ModuleDraftPage> {
  late final TextEditingController jsonController; String error='';
  @override void initState(){super.initState();jsonController=TextEditingController(text:const JsonEncoder.withIndent('  ').convert(widget.initial??{}));}
  @override Widget build(BuildContext c)=>Scaffold(appBar:AppBar(title:Text(widget.initial==null?'New ${widget.module} record':'Edit ${widget.module} record')),body:Padding(padding:const EdgeInsets.all(16),child:Column(children:[const Text('Enter the record fields as JSON. It will be saved on this device and queued for sync.'),Expanded(child:TextField(controller:jsonController,maxLines:null,expands:true,decoration:const InputDecoration(border:OutlineInputBorder(),hintText:'{"field":"value"}'))),if(error.isNotEmpty)Text(error,style:const TextStyle(color:Colors.red)),FilledButton(onPressed:()async{try{final data=Map<String,dynamic>.from(jsonDecode(jsonController.text));await LocalStore.saveModuleRecord(widget.module,data,recordId:widget.initial?['_local_record_id']?.toString()??widget.initial?['id']?.toString(),baseSnapshot:widget.initial?['_base_snapshot'] is Map ? Map<String,dynamic>.from(widget.initial!['_base_snapshot'] as Map) : widget.initial);if(c.mounted)Navigator.pop(c);}catch(e){setState(()=>error='Invalid JSON: $e');}},child:const Text('Save offline'))])));
}


class LeadDraftPage extends StatefulWidget { final Map<String,Object?> initial; const LeadDraftPage({super.key,required this.initial}); @override State<LeadDraftPage> createState()=>_LeadDraftPageState(); }
class _LeadDraftPageState extends State<LeadDraftPage> {
  late final TextEditingController jsonController; String error='';
  @override void initState(){super.initState();final raw=widget.initial['payload'];final data=raw is String?Map<String,dynamic>.from(jsonDecode(raw)):Map<String,dynamic>.from(widget.initial);jsonController=TextEditingController(text:const JsonEncoder.withIndent('  ').convert(data));}
  @override Widget build(BuildContext c)=>Scaffold(appBar:AppBar(title:const Text('Edit lead offline')),body:Padding(padding:const EdgeInsets.all(16),child:Column(children:[const Text('Edit lead fields as JSON. Changes queue locally and sync when connected.'),Expanded(child:TextField(controller:jsonController,maxLines:null,expands:true,decoration:const InputDecoration(border:OutlineInputBorder()))),if(error.isNotEmpty)Text(error,style:const TextStyle(color:Colors.red)),FilledButton(onPressed:()async{try{final data=Map<String,dynamic>.from(jsonDecode(jsonController.text));await LocalStore.saveLead(data);if(c.mounted)Navigator.pop(c);}catch(e){setState(()=>error='Invalid JSON: $e');}},child:const Text('Save offline'))])));
}
