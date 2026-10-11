"""Live host ports and configured service controls."""
from datetime import datetime
from nicegui import ui, run
from services import port_manager


def render_ports_content():
    rows = []
    pending = {}
    busy = False
    refreshing = False
    with ui.column().classes('w-full gap-4'):
        with ui.row().classes('w-full justify-between items-center'):
            status = ui.label('Loading host sockets…').classes('text-sm').style('color:var(--muted)')
            refresh_button = ui.button('Refresh', icon='refresh').props('flat no-caps')
        error_label = ui.label().classes('text-sm text-red-500')
        with ui.card().classes('glass-card w-full p-5 gap-4'):
            with ui.row().classes('w-full items-center gap-3'):
                search = ui.input(placeholder='Search port, process or service').props('outlined dense clearable').classes('flex-1')
                protocol = ui.toggle(['All', 'TCP', 'UDP'], value='All').props('no-caps dense')
            token = ui.input('Service control token', password=True, password_toggle_button=True).props('outlined dense').classes('w-full')
            ui.label('Controls apply to the entire configured service. Stopped services remain listed.').classes('text-xs').style('color:var(--muted)')
            columns = [dict(name=k, label=label, field=k, align='left', sortable=k != 'actions')
                       for k, label in [('port','Port'),('status','State'),('actions','Control'),('protocol','Protocol'),('service','Service'),('address','Bind address'),('owner','Process / PID')]]
            table = ui.table(columns=columns, rows=[], row_key='id', pagination={'rowsPerPage':15,'sortBy':'port'}).classes('ports-table w-full')
            table.add_slot('body-cell-actions', '''<q-td :props="props">
                <q-btn v-if="props.row.controllable" flat dense no-caps
                    :color="props.row.running ? 'negative' : 'positive'"
                    :label="props.row.running ? 'Stop' : 'Start'"
                    :disable="props.row.busy"
                    @click="$parent.$emit('service_action', props.row.id)" />
                <span v-else style="color:var(--muted)">Read only</span>
            </q-td>''')
            search.bind_value_to(table,'filter',forward=lambda value: value or '')
            def update_table():
                table.rows = [dict(row,busy=busy) for row in rows if protocol.value == 'All' or row['protocol'] == protocol.value]
                table.update()
            protocol.on_value_change(update_table)
        with ui.dialog() as dialog, ui.card().classes('glass-card p-6 gap-4'):
            title = ui.label().classes('text-lg font-semibold')
            description = ui.label().classes('text-sm')
            with ui.row().classes('w-full justify-end'):
                ui.button('Cancel',on_click=dialog.close).props('flat no-caps')
                async def confirm():
                    nonlocal busy
                    if busy or not pending:
                        return
                    busy = True
                    dialog.close()
                    update_table()
                    try:
                        await run.io_bound(port_manager.control,pending['service_id'],pending['action'],token.value)
                        ui.notify('Service command confirmed',type='positive')
                    except Exception as exc:
                        ui.notify(str(exc),type='negative')
                    finally:
                        busy = False
                        pending.clear()
                        await refresh()
                ui.button('Confirm',on_click=confirm,color='primary').props('no-caps')
        def request(event):
            if busy:
                return
            row = next((r for r in rows if r['id'] == event.args),None)
            if not row or not row['controllable']:
                return
            if not token.value:
                ui.notify('Enter the service control token first',type='warning')
                return
            action = 'stop' if row['running'] else 'start'
            pending.update(service_id=row['service_id'],action=action)
            title.set_text(f"{action.title()} {row['service']}?")
            ports = ', '.join(f"{r['port']}/{r['protocol']}" for r in rows if r['service_id'] == row['service_id'])
            description.set_text(f'This controls the entire service on the dashboard host. Configured ports: {ports}.')
            dialog.open()
        table.on('service_action',request)
        async def refresh():
            nonlocal rows, refreshing
            if busy or refreshing:
                return
            refreshing = True
            refresh_button.disable()
            try:
                rows, errors = await run.io_bound(port_manager.inventory)
                update_table()
                status.set_text(f"{len({r['port'] for r in rows if r['bound']})} occupied ports · updated {datetime.now():%H:%M:%S}")
                error_label.set_text(' · '.join(errors))
            except Exception as exc:
                error_label.set_text(f'Inventory unavailable: {exc}')
            finally:
                refreshing = False
                refresh_button.enable()
        refresh_button.on_click(refresh)
        ui.timer(15,refresh)
        ui.timer(.1,refresh,once=True)
